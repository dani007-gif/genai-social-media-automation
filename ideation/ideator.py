"""LLM2: turn one brief (the JSON saved by LLM1 in data/kpis/) into 4-5 post ideas.

Text in, text out. No images are sent: LLM1 already described them in the brief.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from kpi_extraction.schema import PostKPIs
from llm_backends import DEFAULT_OLLAMA_MODEL, LLMError, ask_claude, ask_ollama

from .prompts import build_system_prompt, build_user_text
from .schema import MAX_IDEAS, MIN_IDEAS, IdeaSet, PostIdea

DEFAULT_CLAUDE_MODEL = os.getenv("SMM_LLM2_MODEL", "claude-opus-5-5")
DEFAULT_EFFORT = os.getenv("SMM_LLM2_EFFORT", "medium")  # Claude only: low | medium | high | xhigh | max
# Ollama only. LLM1 uses 0 because extraction should be exact; ideas should vary, so this is higher.
OLLAMA_TEMPERATURE = float(os.getenv("SMM_LLM2_TEMPERATURE", "0.8"))


class IdeationError(RuntimeError):
    pass


@dataclass
class IdeaResult:
    email_id: str
    subject: str
    backend: str
    model: str
    generated_at: str
    ideas: List[PostIdea]
    usage: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "email_id": self.email_id,
            "subject": self.subject,
            "backend": self.backend,
            "model": self.model,
            "generated_at": self.generated_at,
            "usage": self.usage,
            "ideas": [idea.model_dump() for idea in self.ideas],
        }

    def save(self, out_dir: str = "data/ideas") -> Path:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / f"{self.email_id}.json"
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False))
        return path


class Ideator:
    def __init__(
        self,
        backend: str = "claude",
        model: Optional[str] = None,
        effort: Optional[str] = None,
        count: int = MAX_IDEAS,
    ):
        if backend not in ("claude", "ollama"):
            raise ValueError(f"Unknown backend: {backend}")
        if not MIN_IDEAS <= count <= MAX_IDEAS:
            raise ValueError(f"count must be between {MIN_IDEAS} and {MAX_IDEAS}")
        self.backend = backend
        self.model = model or (DEFAULT_CLAUDE_MODEL if backend == "claude" else DEFAULT_OLLAMA_MODEL)
        self.effort = effort or DEFAULT_EFFORT
        self.count = count

    def generate(self, brief: dict) -> IdeaResult:
        """`brief` is the content of one data/kpis/<id>.json file."""
        email_id = brief.get("email_id", "unknown")
        try:
            kpis = PostKPIs.model_validate(brief["kpis"])
        except (KeyError, ValueError) as e:
            raise IdeationError(f"{email_id}: this is not a brief saved by LLM1 ({e})") from e
        if not kpis.is_post_request:
            raise IdeationError(f"{email_id}: not a post request, so there is nothing to ideate on.")

        system = build_system_prompt(self.count)
        user_text = build_user_text(kpis.model_dump(), self.count)
        try:
            if self.backend == "claude":
                answer = ask_claude(IdeaSet, system, user_text, model=self.model, effort=self.effort)
            else:
                answer = ask_ollama(IdeaSet, system, user_text, model=self.model, temperature=OLLAMA_TEMPERATURE)
        except LLMError as e:
            raise IdeationError(f"{email_id}: {e}") from e

        ideas = answer.parsed.ideas
        for number, idea in enumerate(ideas, start=1):  # make sure the ids are 1..n, whatever the model wrote
            idea.idea_id = number

        return IdeaResult(
            email_id=email_id,
            subject=brief.get("subject", ""),
            backend=self.backend,
            model=answer.model,
            generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            ideas=ideas,
            usage=answer.usage,
        )
