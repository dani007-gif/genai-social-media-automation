"""Data models produced by the email intake step and consumed by LLM1 (KPI extraction)."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import List, Optional

IMAGE_MIME_PREFIX = "image/"


@dataclass
class Attachment:
    filename: str
    mime_type: str
    size_bytes: int
    path: str                      # where the file was saved locally
    is_inline: bool = False        # embedded in the HTML body (e.g. a logo in a signature)
    content_id: Optional[str] = None

    @property
    def is_image(self) -> bool:
        return self.mime_type.startswith(IMAGE_MIME_PREFIX)


@dataclass
class IncomingEmail:
    message_id: str                # provider id (Gmail id or file name for .eml)
    thread_id: Optional[str]
    sender: str
    sender_email: str
    to: List[str]
    subject: str
    date: Optional[str]            # ISO 8601
    body_text: str                 # plain text, best for the LLM prompt
    body_html: Optional[str] = None
    attachments: List[Attachment] = field(default_factory=list)
    source: str = "gmail"

    @property
    def image_attachments(self) -> List[Attachment]:
        """Images to send to the VLM (logos, sample posts)."""
        return [a for a in self.attachments if a.is_image]

    @property
    def needs_vision(self) -> bool:
        return bool(self.image_attachments)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["needs_vision"] = self.needs_vision
        for a, obj in zip(d["attachments"], self.attachments):
            a["is_image"] = obj.is_image
        return d

    def to_json(self, **kwargs) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, **kwargs)

    @classmethod
    def from_dict(cls, d: dict) -> "IncomingEmail":
        """Rebuild from the JSON saved in data/intake/ (ignores derived keys like needs_vision)."""
        att_fields = {"filename", "mime_type", "size_bytes", "path", "is_inline", "content_id"}
        attachments = [
            Attachment(**{k: v for k, v in a.items() if k in att_fields})
            for a in d.get("attachments", [])
        ]
        return cls(
            message_id=d["message_id"],
            thread_id=d.get("thread_id"),
            sender=d.get("sender", ""),
            sender_email=d.get("sender_email", ""),
            to=d.get("to", []),
            subject=d.get("subject", ""),
            date=d.get("date"),
            body_text=d.get("body_text", ""),
            body_html=d.get("body_html"),
            attachments=attachments,
            source=d.get("source", "gmail"),
        )

    @classmethod
    def load(cls, path: str) -> "IncomingEmail":
        with open(path, encoding="utf-8") as f:
            return cls.from_dict(json.load(f))
