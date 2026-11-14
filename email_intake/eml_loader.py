"""Load a saved .eml file. Useful for testing the pipeline without touching Gmail."""
from __future__ import annotations

from pathlib import Path

from .models import IncomingEmail
from .parser import parse_raw_email


def load_eml(path: str, attachments_dir: str = "data/attachments") -> IncomingEmail:
    p = Path(path)
    return parse_raw_email(
        p.read_bytes(),
        message_id=p.stem,
        attachments_dir=Path(attachments_dir),
        source="eml",
    )
