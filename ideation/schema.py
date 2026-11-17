"""Structured output of LLM2 (ideation): 4-5 post ideas for one brief.

Each idea is text only. It has to be concrete enough for LLM3 to score it against the brief
and for LLM4 to turn it into the final caption and image.
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

MIN_IDEAS = 4
MAX_IDEAS = 5


class MustHavePlacement(BaseModel):
    requirement: str = Field(description="One must_have item, copied from the brief")
    placement: str = Field(
        description="Where exactly it appears in this idea: in the image (say where), "
        "in the on-image text, or in the caption"
    )


class PostIdea(BaseModel):
    # The model writes the fields in this order. must_have_placement comes before visual on
    # purpose: it decides where each requirement goes first, then describes an image that shows it.
    idea_id: int = Field(description="1 for the first idea, 2 for the second, and so on")
    title: str = Field(description="Short working name for the idea")
    angle: str = Field(description="A short phrase: the creative angle that makes this idea different from the others")
    concept: str = Field(description="Two or three sentences: what the post communicates and why it serves the objective")
    must_have_placement: List[MustHavePlacement] = Field(description="One entry for every must_have in the brief")
    visual: str = Field(
        description="What the image shows: subject, setting, colours, layout, and where the logo and any text sit"
    )
    on_image_text: Optional[str] = Field(description="All text written on the image; null if the image has no text")
    caption_hook: str = Field(description="First line of the caption")
    call_to_action: Optional[str] = Field(description="What the audience should do; null if none")
    nice_to_haves_used: List[str] = Field(description="The nice_to_have items this idea uses")
    assumptions: List[str] = Field(description="Choices made that the brief did not specify; empty if none")


class IdeaSet(BaseModel):
    ideas: List[PostIdea] = Field(min_length=MIN_IDEAS, max_length=MAX_IDEAS)
