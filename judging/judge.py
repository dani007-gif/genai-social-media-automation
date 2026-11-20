"""LLM3: score every idea from LLM2 against the brief from LLM1, and pick one.

The judge is the Laya decision model (laya_judge.py), running on this computer. Claude and Ollama
are used for LLM1 and LLM2 only.

One Laya call per idea. Judging ideas one at a time keeps each input inside Laya's 1024-token
window and stops the judge from favouring an idea because of where it sits in a list.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, List, Optional

from pydantic import ValidationError

from ideation.prompts import clean_brief
from ideation.schema import IdeaSet
from kpi_extraction.schema import PostKPIs
from llm_backends import LLMError

from .laya_judge import ask_laya_verdict, resolve_laya_model
from .schema import Decision, IdeaJudgement
from .scoring import PENALTY_PER_PROBLEM, WEIGHTS, decide, score_idea


class JudgingError(RuntimeError):
    pass


@dataclass
class JudgeResult:
    email_id: str
    subject: str
    backend: str
    model: str
    judged_at: str
    decision: Decision
    judgements: List[IdeaJudgement]
    usage: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "email_id": self.email_id,
            "subject": self.subject,
            "backend": self.backend,
            "model": self.model,
            "judged_at": self.judged_at,
            "usage": self.usage,
            "scoring": {"weights": WEIGHTS, "penalty_per_problem": PENALTY_PER_PROBLEM},
            **self.decision.model_dump(),
            "judgements": [j.model_dump() for j in self.judgements],
        }

    def save(self, out_dir: str = "data/judgements") -> Path:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / f"{self.email_id}.json"
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False))
        return path


class Judge:
    backend = "laya"  # the only judge; saved in every judgement file

    def __init__(self, model: Optional[str] = None):
        # A Laya checkpoint: "multilingual" (default), "english", or "auto" to let Laya choose.
        self.model = resolve_laya_model(model)

    def judge(
        self,
        brief: dict,
        ideas: dict,
        on_idea_done: Optional[Callable[[IdeaJudgement], None]] = None,
    ) -> JudgeResult:
        """`brief` is one data/kpis/<id>.json file, `ideas` the matching data/ideas/<id>.json file.
        `on_idea_done` is called after each idea, so the caller can show progress."""
        email_id = brief.get("email_id", "unknown")
        if ideas.get("email_id") != email_id:
            raise JudgingError(f"{email_id}: the ideas file belongs to email {ideas.get('email_id')}")
        try:
            kpis = PostKPIs.model_validate(brief["kpis"])
            idea_list = IdeaSet.model_validate({"ideas": ideas["ideas"]}).ideas
        except (KeyError, ValidationError) as e:
            raise JudgingError(f"{email_id}: brief or ideas file is not in the expected format ({e})") from e
        if not kpis.is_post_request:
            raise JudgingError(f"{email_id}: not a post request, so there is nothing to judge.")

        cleaned = clean_brief(kpis.model_dump())
        must_haves = cleaned.get("must_have", [])
        brief_text = json.dumps(cleaned, ensure_ascii=False)
        judgements: List[IdeaJudgement] = []
        usage = {"input_tokens": 0, "output_tokens": 0}
        model_used = self.model

        for idea in idea_list:
            try:
                # Laya answers typed questions about the idea (laya_judge.py), not a prompt.
                answer = ask_laya_verdict(cleaned, idea.model_dump(), model=self.model)
            except LLMError as e:
                raise JudgingError(f"{email_id}, idea {idea.idea_id}: {e}") from e
            for key in usage:
                usage[key] += answer.usage.get(key, 0)
            model_used = answer.model

            judgement = score_idea(idea, answer.parsed, must_haves, brief_text)
            judgements.append(judgement)
            if on_idea_done:
                on_idea_done(judgement)

        return JudgeResult(
            email_id=email_id,
            subject=brief.get("subject", ""),
            backend=self.backend,
            model=model_used,
            judged_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            decision=decide(judgements, idea_list),
            judgements=judgements,
            usage=usage,
        )
