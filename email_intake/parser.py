"""Turn a raw RFC 822 message (bytes) into an IncomingEmail.

Gmail (format='raw') and local .eml files both go through this one parser.
"""
from __future__ import annotations

import email
import html
import mimetypes
import re
from email import policy
from email.message import EmailMessage
from email.utils import getaddresses, parseaddr, parsedate_to_datetime
from pathlib import Path
from typing import List, Optional, Tuple

from .models import Attachment, IncomingEmail

# Attachments larger than this are skipped (keeps junk like big videos out of the pipeline).
MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def parse_raw_email(
    raw: bytes,
    message_id: str,
    attachments_dir: Path,
    thread_id: Optional[str] = None,
    source: str = "gmail",
) -> IncomingEmail:
    msg: EmailMessage = email.message_from_bytes(raw, policy=policy.default)  # type: ignore[assignment]

    sender_name, sender_email = parseaddr(str(msg.get("From", "")))
    to = [addr for _, addr in getaddresses([str(v) for v in msg.get_all("To", [])]) if addr]

    text, html_body = _extract_bodies(msg)
    if not text and html_body:
        text = _html_to_text(html_body)

    attachments = _save_attachments(msg, attachments_dir / _safe(message_id))

    return IncomingEmail(
        message_id=message_id,
        thread_id=thread_id,
        sender=sender_name or sender_email,
        sender_email=sender_email.lower(),
        to=to,
        subject=str(msg.get("Subject", "")).strip(),
        date=_parse_date(msg.get("Date")),
        body_text=_strip_quoted_reply(text).strip(),
        body_html=html_body,
        attachments=attachments,
        source=source,
    )


def _extract_bodies(msg: EmailMessage) -> Tuple[str, Optional[str]]:
    text_part = msg.get_body(preferencelist=("plain",))
    html_part = msg.get_body(preferencelist=("html",))
    text = text_part.get_content() if text_part else ""
    html_body = html_part.get_content() if html_part else None
    return text, html_body


def _save_attachments(msg: EmailMessage, out_dir: Path) -> List[Attachment]:
    results: List[Attachment] = []
    used_names: set = set()

    for part in msg.walk():
        if part.is_multipart():
            continue
        disposition = part.get_content_disposition()  # 'attachment', 'inline' or None
        mime_type = part.get_content_type()
        filename = part.get_filename()
        content_id = (part.get("Content-ID") or "").strip("<> ") or None

        is_file = disposition == "attachment" or filename
        is_inline_image = mime_type.startswith("image/") and (disposition == "inline" or content_id)
        if not (is_file or is_inline_image):
            continue  # it's a body part

        payload = part.get_payload(decode=True) or b""
        if not payload or len(payload) > MAX_ATTACHMENT_BYTES:
            continue

        if not filename:
            ext = mimetypes.guess_extension(mime_type) or ".bin"
            filename = f"{content_id or 'inline'}{ext}"
        name = _unique(_safe(filename), used_names)

        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / name
        path.write_bytes(payload)

        results.append(
            Attachment(
                filename=filename,
                mime_type=mime_type,
                size_bytes=len(payload),
                path=str(path.resolve()),
                is_inline=disposition != "attachment",
                content_id=content_id,
            )
        )
    return results


def _html_to_text(html_body: str) -> str:
    s = re.sub(r"(?is)<(script|style).*?</\1>", "", html_body)
    s = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>|</h\d>", "\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    return re.sub(r"\n\s*\n+", "\n\n", s)


def _strip_quoted_reply(text: str) -> str:
    """Drop the quoted thread below 'On ... wrote:' so the LLM sees only the new request."""
    m = re.search(r"(?m)^On .{0,200}wrote:\s*$", text)
    if m:
        text = text[: m.start()]
    return "\n".join(line for line in text.splitlines() if not line.startswith(">"))


def _parse_date(value) -> Optional[str]:
    if not value:
        return None
    try:
        return parsedate_to_datetime(str(value)).isoformat()
    except (TypeError, ValueError):
        return None


def _safe(name: str) -> str:
    return _SAFE_NAME.sub("_", name).strip("._") or "file"


def _unique(name: str, used: set) -> str:
    stem, dot, ext = name.rpartition(".")
    if not dot:
        stem, ext = name, ""
    candidate, i = name, 1
    while candidate in used:
        candidate = f"{stem}_{i}.{ext}" if ext else f"{stem}_{i}"
        i += 1
    used.add(candidate)
    return candidate
