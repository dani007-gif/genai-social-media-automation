"""LLM3 (judge): what the model returns for one idea, and the scored record that is saved.

The model only gives checks and 1-5 scores, each with its reason. The code turns those into a
total score and picks the winner (judging/scoring.py), because a small model's arithmetic and
final pick are less reliable than its judgement of one idea at a time.

Every rule break and invented claim must quote the idea. The code checks that the quote really
is in the idea, so a claim the model made up about the idea is ignored.
"""
from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, Field

from ideation.schema import PostIdea

# An enum instead of min/max: both Ollama and Claude can force a value from a fixed list.
Score = Literal[1, 2, 3, 4, 5]


class MustHaveCheck(BaseModel):
    # evidence comes before met on purpose: the model looks first, then decides.
    requirement: str = Field(description="One must_have item, copied from the brief")
    evidence: str = Field(description="Where the idea shows it (quote the idea), or what is missing")
    met: bool = Field(description="true only if the idea clearly includes it")


class NotToHaveCheck(BaseModel):
    rule: str = Field(description="One not_to_have item, copied from the brief")
    quote: str = Field(description="The exact words in the idea that break the rule; empty string if nothing does")
    broken: bool = Field(description="true only if the quote shows the idea breaks the rule")


class InventedClaim(BaseModel):
    quote: str = Field(description="The exact words copied from the idea")
    why_unsupported: str = Field(description="Why the brief does not support this claim")


class CriterionScore(BaseModel):
    reason: str = Field(description="One or two sentences that point to parts of the idea")
    score: Score = Field(description="1 to 5, using the scale in the instructions")


class IdeaVerdict(BaseModel):
    """The model's answer for one idea. Hard rules first, then quality scores, then a summary."""

    must_have_checks: List[MustHaveCheck] = Field(description="One entry for every must_have in the brief")
    not_to_have_checks: List[NotToHaveCheck] = Field(description="One entry for every not_to_have in the brief")
    invented_facts: List[InventedClaim] = Field(
        description="Claims about the product or business that the brief does not support; empty list if none"
    )
    relevance: CriterionScore = Field(
        description="Serves the brief's objective, theme, key message and call to action"
    )
    audience_and_tone: CriterionScore = Field(
        description="Speaks to the target audience in the brief's tone and brand"
    )
    format_fit: CriterionScore = Field(
        description="Works for the platform, format and size; logo spot respected; on-image text short"
    )
    clarity: CriterionScore = Field(
        description="Specific enough for a designer and copywriter to build without guessing"
    )
    summary: str = Field(description="One sentence: the main strength and the main weakness")


class IdeaJudgement(BaseModel):
    """One idea after scoring. This is what is saved, not what the model returns."""

    idea_id: int
    title: str
    passed_hard_rules: bool       # every must_have met and no not_to_have broken
    failed_rules: List[str]       # why it did not pass, if it did not
    problems: List[str]           # smaller issues, including invented claims; each one costs points
    ignored_claims: List[str]     # model claims dropped by the code, because the quote is not in the idea
    quality_score: float          # 0-100, from the four 1-5 scores and their weights
    penalty: float                # points taken off for problems and invented facts
    final_score: float            # quality_score - penalty, never below 0
    verdict: IdeaVerdict          # the model's full answer, so every score has its reason


class Decision(BaseModel):
    winner_idea_id: int
    ranking: List[int]            # idea ids, best first
    needs_review: bool            # true when a person should look before LLM4 uses the winner
    review_reasons: List[str]
    winner: PostIdea              # full copy, so LLM4 needs only this file and the brief
