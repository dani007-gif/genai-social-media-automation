"""LLM3 (judge): turn the model's checks and scores into a total, and pick the winner.

Plain code, no model calls, so the same verdicts always give the same winner.
"""
from __future__ import annotations

import re
from typing import List, Tuple

from ideation.schema import PostIdea

from .schema import Decision, IdeaJudgement, IdeaVerdict

# How much each quality score counts. They add up to 1. Relevance to the brief counts most,
# because that is what the customer asked for.
WEIGHTS = {
    "relevance": 0.40,
    "audience_and_tone": 0.25,
    "format_fit": 0.20,
    "clarity": 0.15,
}
PENALTY_PER_PROBLEM = 10.0  # points off (out of 100) for each problem or invented fact

_ON_IMAGE_TEXT = re.compile(r"on[- ]?image text", re.IGNORECASE)
_WORD = re.compile(r"[a-z0-9]+(?:[.,][0-9]+)?")


def quality_score(verdict: IdeaVerdict) -> float:
    """The four 1-5 scores, weighted, as a number from 0 (all 1s) to 100 (all 5s)."""
    weighted = sum(getattr(verdict, name).score * weight for name, weight in WEIGHTS.items())
    return round((weighted - 1) / 4 * 100, 1)


def code_checks(must_haves: List[str], idea: PostIdea) -> Tuple[List[str], List[str]]:
    """Checks that do not need a model. Returns (failed hard rules, smaller problems)."""
    failed: List[str] = []
    problems: List[str] = []

    requirements = [p.requirement for p in idea.must_have_placement]
    for item in must_haves:
        if not any(_same_requirement(item, req) for req in requirements):
            failed.append(f"must_have_placement has no entry for: {item}")

    if not (idea.on_image_text or "").strip():
        for p in idea.must_have_placement:
            if _ON_IMAGE_TEXT.search(p.placement):
                problems.append(f"'{p.requirement}' is placed in the on-image text, but on_image_text is empty")

    return failed, problems


def score_idea(idea: PostIdea, verdict: IdeaVerdict, must_haves: List[str], brief_text: str) -> IdeaJudgement:
    """`brief_text` is the cleaned brief as text, used to drop "invented" claims the brief does support."""
    failed, problems = code_checks(must_haves, idea)
    ignored: List[str] = []
    idea_text = _idea_text(idea)

    for check in verdict.must_have_checks:
        if check.met:
            continue
        # The full caption is written later by LLM4, so "in the caption" is a valid place,
        # even when the model cannot see the requirement in this idea's text yet.
        if any(_same_requirement(check.requirement, p.requirement) and "caption" in p.placement.lower()
               for p in idea.must_have_placement):
            ignored.append(f"must_have '{check.requirement}': placed in the caption, which LLM4 writes later")
        else:
            failed.append(f"must_have not met: {check.requirement} ({check.evidence})")

    # A rule break or invented claim only counts if its quote is really in the idea.
    for check in verdict.not_to_have_checks:
        if not check.broken:
            continue
        if _contains(idea_text, check.quote):
            failed.append(f"breaks not_to_have: {check.rule} (\"{check.quote}\")")
        else:
            ignored.append(f"not_to_have '{check.rule}': quote not found in the idea (\"{check.quote}\")")

    for claim in verdict.invented_facts:
        if not _contains(idea_text, claim.quote):
            ignored.append(f"invented fact: quote not found in the idea (\"{claim.quote}\")")
        elif _contains(brief_text, claim.quote):
            ignored.append(f"invented fact: the brief does say this (\"{claim.quote}\")")
        else:
            problems.append(f"claim not in the brief: \"{claim.quote}\" ({claim.why_unsupported})")

    quality = quality_score(verdict)
    penalty = PENALTY_PER_PROBLEM * len(problems)
    return IdeaJudgement(
        idea_id=idea.idea_id,
        title=idea.title,
        passed_hard_rules=not failed,
        failed_rules=failed,
        problems=problems,
        ignored_claims=ignored,
        quality_score=quality,
        penalty=penalty,
        final_score=max(0.0, round(quality - penalty, 1)),
        verdict=verdict,
    )


def decide(judgements: List[IdeaJudgement], ideas: List[PostIdea]) -> Decision:
    """Ideas that pass the hard rules come first, then the highest final score wins.
    Ties go to the idea with fewer problems, then higher relevance, then the lower idea number."""
    ranked = sorted(
        judgements,
        key=lambda j: (not j.passed_hard_rules, -j.final_score, j.penalty,
                       -j.verdict.relevance.score, j.idea_id),
    )
    best = ranked[0]

    reasons: List[str] = []
    if not best.passed_hard_rules:
        reasons.append("No idea passed every hard rule, so the highest score was picked: "
                       + "; ".join(best.failed_rules))
    if best.problems:
        reasons.append("The winner has problems: " + "; ".join(best.problems))
    if len(ranked) > 1 and ranked[1].passed_hard_rules == best.passed_hard_rules \
            and best.final_score - ranked[1].final_score < 5:
        reasons.append(f"Close call: idea {ranked[1].idea_id} scored {ranked[1].final_score} "
                       f"against {best.final_score}.")

    return Decision(
        winner_idea_id=best.idea_id,
        ranking=[j.idea_id for j in ranked],
        needs_review=bool(reasons),
        review_reasons=reasons,
        winner=_find(ideas, best.idea_id),
    )


def _same_requirement(must_have: str, requirement: str) -> bool:
    """True if `requirement` is the brief's must_have, allowing small rewording by the model."""
    wanted = _words(must_have)
    if not wanted:
        return True
    return len(wanted & _words(requirement)) / len(wanted) >= 0.6


def _idea_text(idea: PostIdea) -> str:
    """The parts of an idea that end up in the post (or describe it), as one text."""
    parts = [idea.concept, idea.visual, idea.on_image_text, idea.caption_hook, idea.call_to_action]
    parts += [p.placement for p in idea.must_have_placement]
    return "\n".join(p for p in parts if p)


def _contains(text: str, quote: str) -> bool:
    """True if `quote` appears in `text`, ignoring case, punctuation and spacing."""
    wanted = _normalise(quote)
    return bool(wanted) and wanted in _normalise(text)


def _normalise(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def _words(text: str) -> set:
    return {w for w in _WORD.findall(text.lower()) if len(w) > 2 or any(c.isdigit() for c in w)}


def _find(ideas: List[PostIdea], idea_id: int) -> PostIdea:
    return next(idea for idea in ideas if idea.idea_id == idea_id)
