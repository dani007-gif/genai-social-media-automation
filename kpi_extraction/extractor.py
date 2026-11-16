"""LLM1: turn an IncomingEmail into a structured post brief (PostKPIs).

One Claude call does both the text extraction and the image analysis: Claude reads images
natively, so the "VLM" part is just image blocks added to the same request when the email has
images (IncomingEmail.needs_vision).
"""
from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import anthropic

from email_intake.models import Attachment, IncomingEmail

from .prompts import SYSTEM_PROMPT, build_user_text
from .schema import PostKPIs

DEFAULT_MODEL = os.getenv("SMM_LLM1_MODEL", "claude-opus-5-5")
DEFAULT_EFFORT = os.getenv("SMM_LLM1_EFFORT", "medium")  # low | medium | high | xhigh | max

# Image limits for the API: these media types only, 5 MB per image.
SUPPORTED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGES = 20


class ExtractionError(RuntimeError):
    pass


@dataclass
class KPIResult:
    email_id: str
    subject: str
    sender_email: str
    model: str
    extracted_at: str
    kpis: PostKPIs
    images_sent: List[str] = field(default_factory=list)
    images_skipped: List[str] = field(default_factory=list)
    usage: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "email_id": self.email_id,
            "subject": self.subject,
            "sender_email": self.sender_email,
            "model": self.model,
            "extracted_at": self.extracted_at,
            "images_sent": self.images_sent,
            "images_skipped": self.images_skipped,
            "usage": self.usage,
            "kpis": self.kpis.model_dump(),
        }

    def save(self, out_dir: str = "data/kpis") -> Path:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / f"{self.email_id}.json"
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False))
        return path


class KPIExtractor:
    def __init__(
        self,
        client: Optional[anthropic.Anthropic] = None,
        model: str = DEFAULT_MODEL,
        effort: str = DEFAULT_EFFORT,
    ):
        # Reads ANTHROPIC_API_KEY from the environment.
        self.client = client or anthropic.Anthropic()
        self.model = model
        self.effort = effort

    def build_content(self, em: IncomingEmail):
        """User message content: images first (each labelled with its filename), then the email text."""
        content: list = []
        sent: List[str] = []
        skipped: List[str] = []

        for att in em.image_attachments:
            reason = _skip_reason(att, len(sent))
            if reason:
                skipped.append(f"{att.filename} ({reason})")
                continue
            kind = "inline image in the email body" if att.is_inline else "attached file"
            content.append({"type": "text", "text": f"Image filename: {att.filename} ({kind})"})
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": att.mime_type,
                        "data": base64.standard_b64encode(Path(att.path).read_bytes()).decode("ascii"),
                    },
                }
            )
            sent.append(att.filename)

        other_files = [a.filename for a in em.attachments if not a.is_image]
        body = em.body_text or "(empty body)"
        if other_files:
            body += "\n\n[Non-image attachments, not shown: " + ", ".join(other_files) + "]"
        if skipped:
            body += "\n\n[Images that could not be shown: " + ", ".join(skipped) + "]"

        content.append(
            {
                "type": "text",
                "text": build_user_text(
                    subject=em.subject,
                    sender=f"{em.sender} <{em.sender_email}>",
                    date=em.date or "unknown",
                    body=body,
                ),
            }
        )
        return content, sent, skipped

    def extract(self, em: IncomingEmail) -> KPIResult:
        content, sent, skipped = self.build_content(em)

        try:
            response = self.client.beta.messages.parse(
                model=self.model,
                max_tokens=16000,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": content}],
                output_format=PostKPIs,
                output_config={"effort": self.effort},
                # If a safety classifier declines, the API retries on a suitable fallback model.
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except anthropic.AuthenticationError as e:
            raise ExtractionError("Invalid or missing ANTHROPIC_API_KEY.") from e
        except anthropic.BadRequestError as e:
            raise ExtractionError(f"Request rejected by the API: {e.message}") from e
        except anthropic.RateLimitError as e:
            raise ExtractionError("Rate limited by the API (after SDK retries). Try again later.") from e
        except anthropic.APIStatusError as e:
            raise ExtractionError(f"API error {e.status_code}: {e.message}") from e
        except anthropic.APIConnectionError as e:
            raise ExtractionError("Could not reach the Anthropic API. Check your connection.") from e

        if response.stop_reason == "refusal":
            raise ExtractionError(f"Model declined to process email {em.message_id}.")
        if response.stop_reason == "max_tokens":
            raise ExtractionError(f"Output was cut off for email {em.message_id} (max_tokens).")
        if response.parsed_output is None:
            raise ExtractionError(f"No structured output returned for email {em.message_id}.")

        u = response.usage
        return KPIResult(
            email_id=em.message_id,
            subject=em.subject,
            sender_email=em.sender_email,
            model=response.model,
            extracted_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            kpis=response.parsed_output,
            images_sent=sent,
            images_skipped=skipped,
            usage={"input_tokens": u.input_tokens, "output_tokens": u.output_tokens},
        )


def _skip_reason(att: Attachment, already_sent: int) -> Optional[str]:
    if att.mime_type not in SUPPORTED_IMAGE_TYPES:
        return f"unsupported type {att.mime_type}"
    if att.size_bytes > MAX_IMAGE_BYTES:
        return "larger than 5 MB"
    if already_sent >= MAX_IMAGES:
        return f"more than {MAX_IMAGES} images"
    if not Path(att.path).exists():
        return "file missing on disk"
    return None
