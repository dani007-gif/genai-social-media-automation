"""LLM1 on a local model: same job as extractor.py, but the model runs on this computer with Ollama.

Ollama's API is a small web server on this machine. It needs no key and nothing leaves the computer.
"""
from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from email_intake.models import IncomingEmail

from .extractor import ExtractionError, KPIResult, _skip_reason
from .prompts import SYSTEM_PROMPT, build_user_text
from .schema import PostKPIs

OLLAMA_URL = os.getenv("SMM_OLLAMA_URL", "http://localhost:11434/api/chat")
DEFAULT_MODEL = os.getenv("SMM_OLLAMA_MODEL", "gemma4:e2b-it-qat")
# How many tokens (email + images + answer) the model can read at once. An email that needs more
# gives a clear error. 20480 fits the longest email saved so far (17,320 tokens) plus its answer.
DEFAULT_NUM_CTX = int(os.getenv("SMM_OLLAMA_NUM_CTX", "20480"))
TIMEOUT_SECONDS = 600

SCHEMA = PostKPIs.model_json_schema()


class OllamaKPIExtractor:
    def __init__(self, model: str = DEFAULT_MODEL, num_ctx: int = DEFAULT_NUM_CTX):
        self.model = model
        self.num_ctx = num_ctx

    def build_message(self, em: IncomingEmail):
        """The user message: the email text plus the images, named in the order they are sent."""
        images, sent, labels, skipped = [], [], [], []
        for att in em.image_attachments:
            reason = _skip_reason(att, len(sent))
            if reason:
                skipped.append(f"{att.filename} ({reason})")
                continue
            images.append(base64.standard_b64encode(Path(att.path).read_bytes()).decode("ascii"))
            kind = "inline image in the email body" if att.is_inline else "attached file"
            labels.append(f"{len(sent) + 1}. Image filename: {att.filename} ({kind})")
            sent.append(att.filename)

        other_files = [a.filename for a in em.attachments if not a.is_image]
        body = em.body_text or "(empty body)"
        if other_files:
            body += "\n\n[Non-image attachments, not shown: " + ", ".join(other_files) + "]"
        if skipped:
            body += "\n\n[Images that could not be shown: " + ", ".join(skipped) + "]"

        text = ""
        if labels:
            text += "Images sent with this message, in this order:\n" + "\n".join(labels) + "\n\n"
        text += build_user_text(
            subject=em.subject,
            sender=f"{em.sender} <{em.sender_email}>",
            date=em.date or "unknown",
            body=body,
        )
        # Ollama forces the answer into the schema's shape, but the model only learns what each
        # field means if the schema is also written in the prompt.
        text += "\n\nAnswer with JSON only, following this JSON schema:\n" + json.dumps(SCHEMA)

        return {"role": "user", "content": text, "images": images}, sent, skipped

    def extract(self, em: IncomingEmail) -> KPIResult:
        message, sent, skipped = self.build_message(em)
        answer = self._call(
            {
                "model": self.model,
                "messages": [{"role": "system", "content": SYSTEM_PROMPT}, message],
                "format": SCHEMA,    # the answer must be JSON matching PostKPIs
                "stream": False,     # one complete answer instead of word-by-word
                "think": False,
                "truncate": False,   # too-long email -> error, instead of silently cutting it
                "shift": False,      # same for the answer: stop instead of dropping earlier text
                "options": {"temperature": 0, "num_ctx": self.num_ctx},
            },
            em,
        )

        if answer.get("done_reason") == "length":
            raise ExtractionError(
                f"The answer for email {em.message_id} was cut off: the context of {self.num_ctx} tokens "
                "is full. Set SMM_OLLAMA_NUM_CTX to a bigger number and try again."
            )
        try:
            kpis = PostKPIs.model_validate_json(answer["message"]["content"])
        except (KeyError, ValidationError) as e:
            raise ExtractionError(f"Model answer for email {em.message_id} did not match the schema: {e}") from e

        return KPIResult(
            email_id=em.message_id,
            subject=em.subject,
            sender_email=em.sender_email,
            model=answer.get("model", self.model),
            extracted_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            kpis=kpis,
            images_sent=sent,
            images_skipped=skipped,
            usage={
                "input_tokens": answer.get("prompt_eval_count", 0),
                "output_tokens": answer.get("eval_count", 0),
            },
        )

    def _call(self, payload: dict, em: IncomingEmail) -> dict:
        """Send one request to Ollama's API and return its JSON answer."""
        request = urllib.request.Request(
            OLLAMA_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as e:  # Ollama answered, but with an error
            detail = e.read().decode("utf-8", errors="replace")
            hint = ""
            if "context size" in detail:
                hint = " The email is too long: set SMM_OLLAMA_NUM_CTX to a bigger number."
            raise ExtractionError(f"Ollama error {e.code} for email {em.message_id}: {detail}{hint}") from e
        except OSError as e:  # nothing listening on the port, or no answer in time
            raise ExtractionError(f"Could not get an answer from Ollama at {OLLAMA_URL}. Is the Ollama app running?") from e
