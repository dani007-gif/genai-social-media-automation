"""LLM3 with Laya (the only judge): turn the brief into typed questions, and Laya's answers into
an IdeaVerdict.

Laya (huggingface.co/convaiinnovations/laya) does not write text, so it cannot fill the IdeaVerdict
the way a chat model would. Instead every part of the verdict becomes one question about the idea:
- each must_have            -> a yes/no question: does the idea include it?
- each not_to_have          -> a yes/no question per idea field: does this field break the rule?
- invented facts            -> a yes/no question per audience-facing field: does it claim
                               something the brief does not say?
- the four quality criteria -> a 1-5 score question, with the scale from the LLM prompt.

Laya cannot quote, so a "quote" here is the whole idea field the question was about. That keeps
the quote checks in scoring.py working: the field is really in the idea, and a field the brief
already says word for word is still dropped as not invented.

The rest of LLM3 (scoring.py: hard rules, weights, penalties, the winner) is unchanged.
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional, Tuple

from llm_backends import LLMAnswer, LLMError, ask_laya

from .schema import CriterionScore, IdeaVerdict, InventedClaim, MustHaveCheck, NotToHaveCheck

# A yes/no answer counts as "yes" from this probability on.
YES_THRESHOLD = float(os.getenv("SMM_LAYA_THRESHOLD", "0.5"))
# "multilingual" reads up to 1024 tokens, the English checkpoint only 512, and a brief plus one
# idea is about 600-850 tokens, so the English one would cut it off. "auto" lets Laya choose.
DEFAULT_LAYA_MODEL = os.getenv("SMM_LAYA_MODEL", "multilingual")
LAYA_MODELS = ("multilingual", "english", "auto")


def resolve_laya_model(model: Optional[str]) -> str:
    """The checkpoint name to judge with: the one asked for, else the default. Rejects anything that
    is not a Laya checkpoint (for example an Ollama model name), before any model is loaded."""
    name = (model or DEFAULT_LAYA_MODEL or "multilingual").strip().lower()
    if name not in LAYA_MODELS:
        raise ValueError(f"Unknown Laya model '{model}'. LLM3 only uses Laya: choose one of {', '.join(LAYA_MODELS)}.")
    return name

# Fields a rule can be broken in, and the ones the audience reads (where invented facts matter).
RULE_FIELDS = ["visual", "on_image_text", "caption_hook", "call_to_action"]
CLAIM_FIELDS = ["on_image_text", "caption_hook", "call_to_action"]

# Same scales as the Claude/Ollama prompt (prompts.py), lowest first: index 0 = score 1.
SCALES: Dict[str, Tuple[str, List[str]]] = {
    "relevance": (
        "Does the idea deliver the brief's objective, theme and key message, with a call to action "
        "that matches the brief?",
        ["It misses the brief.",
         "Mostly off the brief.",
         "On theme, but the message or objective is weak or generic.",
         "Delivers most of the brief clearly.",
         "Delivers the objective, theme, key message and call to action, clearly."],
    ),
    "audience_and_tone": (
        "Is the idea written for the brief's target audience, in the brief's tone and brand?",
        ["Wrong tone or audience.",
         "Mostly the wrong tone.",
         "Generic, could be any brand.",
         "Mostly fits the audience and brand.",
         "Clearly made for this audience and brand."],
    ),
    "format_fit": (
        "Does the idea work for the brief's platform, format and size, keep the logo spot free, "
        "and keep the on-image text readable at a glance on a phone?",
        ["Does not fit the format.",
         "Needs big changes to fit.",
         "Would work after changes.",
         "Fits with small changes.",
         "Composed for this format."],
    ),
    "clarity": (
        "Could a designer and a copywriter build this idea without asking questions?",
        ["Too vague to build.",
         "Much guessing needed.",
         "Some guessing needed.",
         "Nearly everything is spelled out.",
         "Everything is spelled out."],
    ),
}


def ask_laya_verdict(brief: dict, idea: dict, model: Optional[str] = None) -> LLMAnswer:
    """`brief` is the cleaned brief, `idea` one PostIdea as a dict. Returns an IdeaVerdict.
    `model` is a name from LAYA_MODELS (None = the default)."""
    model = resolve_laya_model(model)
    must_haves = brief.get("must_have", [])
    rules = brief.get("not_to_have", [])
    fields = {f: (idea.get(f) or "").strip() for f in RULE_FIELDS}

    questions: Dict[str, dict] = {}
    for i, item in enumerate(must_haves):
        questions[f"must_{i}"] = _yes_no(
            f"Does the idea clearly include this requirement: \"{item}\"? Look at must_have_placement, "
            "visual, on_image_text, caption_hook and call_to_action. If must_have_placement puts it "
            "in the caption, it counts as included.",
            yes="The idea clearly includes it.", no="The idea does not include it.")
    for i, rule in enumerate(rules):
        for f, text in fields.items():
            if text:
                questions[f"rule_{i}_{f}"] = _yes_no(
                    f"Does the idea's {f} break this rule from the brief: \"{rule}\"? Something the "
                    "text does not mention does not break a rule about it.",
                    yes=f"The {f} breaks the rule.", no=f"The {f} follows the rule.")
    for f in CLAIM_FIELDS:
        if fields.get(f):
            questions[f"claim_{f}"] = _yes_no(
                f"Does the idea's {f} claim a fact about the product or business that the brief does "
                "not state, such as a price, date, discount, availability, scarcity, ordering option "
                "(pre-order, delivery, link in bio), feature, ingredient or award?",
                yes="It claims something the brief does not state.",
                no="Everything it claims is in the brief, or it claims nothing.")
    for name, (instructions, levels) in SCALES.items():
        questions[name] = {"type": "score", "instructions": instructions, "criteria": levels}

    state = {"brief": brief, "idea": _idea_for_state(idea)}
    # "auto" means no pinned checkpoint: Laya picks one from the text's language.
    raw = ask_laya(state, questions, model=None if model == "auto" else model)
    answers = raw["answers"]
    usage = raw.get("usage") or {}
    # Same rule as the Ollama backend: cut-off input is an error, not a silent wrong answer.
    if usage.get("truncated"):
        raise LLMError(
            f"Laya cut off {usage.get('state_tokens_dropped', '?')} tokens of the brief and idea "
            f"({usage.get('state_tokens', '?')} tokens in, model {model}). The multilingual checkpoint "
            "reads 1024 tokens (--judge-model multilingual); if it is already used, the brief or "
            "idea is too long for Laya."
        )

    verdict = IdeaVerdict(
        must_have_checks=[
            MustHaveCheck(
                requirement=item,
                evidence=f"Laya: p(included) = {_p(answers, f'must_{i}'):.2f}",
                met=_p(answers, f"must_{i}") >= YES_THRESHOLD,
            )
            for i, item in enumerate(must_haves)
        ],
        not_to_have_checks=[_rule_check(answers, i, rule, fields) for i, rule in enumerate(rules)],
        invented_facts=[
            InventedClaim(
                quote=fields[f],
                why_unsupported=f"Laya: p(claim not in the brief) = {_p(answers, f'claim_{f}'):.2f}",
            )
            for f in CLAIM_FIELDS
            if fields.get(f) and _p(answers, f"claim_{f}") >= YES_THRESHOLD
        ],
        **{name: _criterion(answers[name]) for name in SCALES},
        summary="",
    )
    verdict.summary = _summary(verdict)

    return LLMAnswer(
        parsed=verdict,
        # The checkpoint that judged (Laya's own "model" field is always "laya-rl-agent").
        model=f"laya:{model}",
        usage={"input_tokens": usage.get("input_tokens", 0), "output_tokens": usage.get("output_tokens", 0)},
    )


def _yes_no(instructions: str, yes: str, no: str) -> dict:
    # Describing both options matters: Laya's card warns that a bare yes/no question can follow
    # the option labels instead of the text.
    return {"type": "noul", "instructions": instructions, "criteria": {"true": yes, "false": no}}


def _p(answers: dict, qid: str) -> float:
    """Probability of "yes" for a yes/no question."""
    return float(answers[qid]["noul"])


def _rule_check(answers: dict, i: int, rule: str, fields: Dict[str, str]) -> NotToHaveCheck:
    # The field most likely to break the rule decides; its text is the quote.
    scored = [(_p(answers, f"rule_{i}_{f}"), f) for f, text in fields.items() if text]
    if not scored:
        return NotToHaveCheck(rule=rule, quote="", broken=False)
    p, f = max(scored)
    broken = p >= YES_THRESHOLD
    return NotToHaveCheck(rule=rule, quote=fields[f] if broken else "", broken=broken)


def _criterion(answer: dict) -> CriterionScore:
    # Laya's score is the expected level index (0 = lowest), not a whole number.
    expected = float(answer["score"])
    score = min(5, max(1, int(round(expected)) + 1))
    return CriterionScore(
        reason=f"Laya: expected level {expected + 1:.2f} of 5 (confidence {float(answer.get('confidence', 0)):.2f})",
        score=score,
    )


def _summary(verdict: IdeaVerdict) -> str:
    scores = {name: getattr(verdict, name).score for name in SCALES}
    best = max(scores, key=scores.get)
    worst = min(scores, key=scores.get)
    return (f"Strongest on {best.replace('_', ' ')} ({scores[best]}/5), "
            f"weakest on {worst.replace('_', ' ')} ({scores[worst]}/5).")


def _idea_for_state(idea: dict) -> dict:
    """Only the parts of the idea Laya needs, to stay inside its short input window."""
    keep = ["title", "concept", "visual", "on_image_text", "caption_hook", "call_to_action",
            "must_have_placement"]
    return {k: idea[k] for k in keep if idea.get(k)}
