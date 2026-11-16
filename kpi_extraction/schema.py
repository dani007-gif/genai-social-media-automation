"""Structured output of LLM1 (KPI extraction).

The API is constrained to return JSON matching `PostKPIs` (structured outputs), so every field is
always present. "Unknown" is expressed as null / empty list, never as a guess.
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field
from typing_extensions import Literal


class PostSize(BaseModel):
    width_px: Optional[int]
    height_px: Optional[int]
    aspect_ratio: Optional[str] = Field(description='e.g. "1:1", "4:5", "9:16"')
    source: Literal["stated_in_email", "platform_default", "not_specified"]


class LogoInfo(BaseModel):
    provided: bool = Field(description="True if one of the attached/inline images is the company logo")
    attachment_filename: Optional[str] = Field(description="Exact filename of the logo attachment, if any")
    placement: Optional[str] = Field(description='e.g. "bottom-right corner, small"')
    placement_source: Literal["stated_in_email", "inferred_from_reference", "not_specified"]


class Company(BaseModel):
    name: Optional[str]
    website: Optional[str]
    industry: Optional[str]
    brand_colors: List[str] = Field(description="Hex codes or color names, stated or seen in the logo")
    logo: LogoInfo


class ReferencePost(BaseModel):
    source: str = Field(description="Attachment filename or URL of the example post")
    what_to_take: str = Field(description="What the customer wants copied from it (style, layout, colors...)")


class ImageAnalysis(BaseModel):
    attachment_filename: str
    role: Literal[
        "logo",
        "sample_post",
        "product_photo",
        "brand_asset",
        "signature_or_decoration",
        "unrelated",
    ]
    description: str
    dominant_colors: List[str]
    notes_for_design: Optional[str] = Field(
        description="Anything the designer should reuse or respect (layout, logo position, fonts...)"
    )


class PostKPIs(BaseModel):
    is_post_request: bool = Field(
        description="False if the email is not a request to create a social media post"
    )
    not_a_request_reason: Optional[str]

    platform: Optional[str] = Field(description='e.g. "Instagram", "LinkedIn"; null if not stated')
    post_format: Literal[
        "feed_post", "story", "reel_or_video", "carousel", "banner", "other", "not_specified"
    ]
    post_size: PostSize
    company: Company

    theme: Optional[str]
    objective: Optional[str] = Field(description="Business goal, e.g. product launch, hiring, event promotion")
    key_message: Optional[str]
    call_to_action: Optional[str]
    target_audience: Optional[str]
    tone: Optional[str]
    post_language: Optional[str] = Field(description="Language the post should be written in")

    must_have: List[str]
    nice_to_have: List[str]
    not_to_have: List[str]
    hashtags: List[str]
    deadline: Optional[str] = Field(description="ISO date if a publish date or deadline is given")

    reference_posts: List[ReferencePost]
    image_analysis: List[ImageAnalysis] = Field(description="One entry per image provided with the email")
    missing_information: List[str] = Field(
        description="Questions to ask the customer before the post can be made well"
    )
