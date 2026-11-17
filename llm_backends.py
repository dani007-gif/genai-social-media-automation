"""One way to ask a model a question and get the answer back in a fixed JSON shape.

Two backends, same result (an LLMAnswer):
- ask_claude: Anthropic API. Paid, needs ANTHROPIC_API_KEY.
- ask_ollama: a model running on this computer. Free, needs the Ollama app to be open.

Used by the text-only LLM steps (LLM2 ideation onwards). LLM1 keeps its own calls in
kpi_extraction/ because it also sends images.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional, Type

from pydantic import BaseModel, ValidationError

# Same environment variables and defaults as kpi_extraction/ollama_extractor.py. Keeping the
# same context size matters: Ollama reloads the model when it changes between two requests.
OLLAMA_URL = os.getenv("SMM_OLLAMA_URL", "http://localhost:11434/api/chat")
DEFAULT_OLLAMA_MODEL = os.getenv("SMM_OLLAMA_MODEL", "gemma4:e2b-it-qat")
DEFAULT_NUM_CTX = int(os.getenv("SMM_OLLAMA_NUM_CTX", "20480"))
OLLAMA_TIMEOUT_SECONDS = 600

DEFAULT_CLAUDE_MODEL = "claude-opus-5-5"
NO_KEY_MESSAGE = (
    "No Anthropic API key found. Set ANTHROPIC_API_KEY, "
    "or add --backend ollama to use the local model."
)


class LLMError(RuntimeError):
    """The model gave no usable answer. The message says what went wrong and what to try."""


@dataclass
class LLMAnswer:
    parsed: BaseModel   # the answer, already checked against the schema
    model: str          # the model that actually answered
    usage: dict         # {"input_tokens": ..., "output_tokens": ...}


def ask_claude(
    schema: Type[BaseModel],
    system: str,
    user_text: str,
    model: str = DEFAULT_CLAUDE_MODEL,
    effort: str = "medium",
    client=None,
) -> LLMAnswer:
    import anthropic  # imported here so the Ollama path works without the package

    client = client or anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
    try:
        response = client.beta.messages.parse(
            model=model,
            max_tokens=16000,
            system=system,
            messages=[{"role": "user", "content": user_text}],
            output_format=schema,  # the answer must be JSON matching the schema
            output_config={"effort": effort},
            # If a safety classifier declines, the API retries on a suitable fallback model.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
    except ValidationError as e:
        raise LLMError(f"The answer did not match the expected shape: {_short(e)}") from e
    except TypeError as e:  # the SDK raises this when it finds no API key at all
        if "authentication" not in str(e).lower():
            raise
        raise LLMError(NO_KEY_MESSAGE) from e
    except anthropic.AuthenticationError as e:
        raise LLMError("Invalid or missing ANTHROPIC_API_KEY.") from e
    except anthropic.BadRequestError as e:
        raise LLMError(f"Request rejected by the API: {e.message}") from e
    except anthropic.RateLimitError as e:
        raise LLMError("Rate limited by the API (after SDK retries). Try again later.") from e
    except anthropic.APIStatusError as e:
        raise LLMError(f"API error {e.status_code}: {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise LLMError("Could not reach the Anthropic API. Check your connection.") from e

    if response.stop_reason == "refusal":
        raise LLMError("The model declined to answer.")
    if response.stop_reason == "max_tokens":
        raise LLMError("The answer was cut off (max_tokens).")
    if response.parsed_output is None:
        raise LLMError("No structured answer came back.")

    return LLMAnswer(
        parsed=response.parsed_output,
        model=response.model,
        usage={
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        },
    )


def ask_ollama(
    schema: Type[BaseModel],
    system: str,
    user_text: str,
    model: str = DEFAULT_OLLAMA_MODEL,
    num_ctx: int = DEFAULT_NUM_CTX,
    temperature: float = 0.0,
) -> LLMAnswer:
    json_schema = schema.model_json_schema()
    # Ollama forces the answer into the schema's shape, but the model only learns what each
    # field means if the schema is also written in the prompt.
    user_text += "\n\nAnswer with JSON only, following this JSON schema:\n" + json.dumps(json_schema)

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_text},
        ],
        "format": json_schema,
        "stream": False,     # one complete answer instead of word-by-word
        "think": False,
        "truncate": False,   # too-long input -> error, instead of silently cutting it
        "shift": False,      # same for the answer: stop instead of dropping earlier text
        "options": {"temperature": temperature, "num_ctx": num_ctx},
    }
    request = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=OLLAMA_TIMEOUT_SECONDS) as response:
            answer = json.loads(response.read())
    except urllib.error.HTTPError as e:  # Ollama answered, but with an error
        detail = e.read().decode("utf-8", errors="replace")
        hint = " Set SMM_OLLAMA_NUM_CTX to a bigger number." if "context size" in detail else ""
        raise LLMError(f"Ollama error {e.code}: {detail}{hint}") from e
    except OSError as e:  # nothing listening on the port, or no answer in time
        raise LLMError(f"Could not get an answer from Ollama at {OLLAMA_URL}. Is the Ollama app running?") from e

    if answer.get("done_reason") == "length":
        raise LLMError(
            f"The answer was cut off: the context of {num_ctx} tokens is full. "
            "Set SMM_OLLAMA_NUM_CTX to a bigger number and try again."
        )
    try:
        parsed = schema.model_validate_json(answer["message"]["content"])
    except (KeyError, ValidationError) as e:
        raise LLMError(f"The answer did not match the expected shape: {_short(e)}") from e

    return LLMAnswer(
        parsed=parsed,
        model=answer.get("model", model),
        usage={
            "input_tokens": answer.get("prompt_eval_count", 0),
            "output_tokens": answer.get("eval_count", 0),
        },
    )


def _short(error: Exception, limit: int = 300) -> str:
    text = " ".join(str(error).split())
    return text if len(text) <= limit else text[:limit] + "..."
