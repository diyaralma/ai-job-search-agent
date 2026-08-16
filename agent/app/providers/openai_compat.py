"""Provider for OpenAI and every OpenAI-compatible endpoint.

Since this is a single `POST {base_url}/chat/completions`, it uses httpx — which
the project already depends on — rather than the official SDK: OpenRouter, Groq,
Together, DeepSeek, Ollama, LM Studio and vLLM all speak this contract but differ
in which parameters they accept. Building the body ourselves lets us notice an
unsupported field and step back.

The two points where they diverge, and how each is handled:

1. **Schema enforcement.** OpenAI supports `response_format.json_schema`, most
   local servers do not. With LLM_JSON_MODE=auto we start at the strongest mode,
   fall back to `json_object` on a 400, and finally to putting the schema in the
   system prompt as free text. The working mode is remembered — it is not
   re-negotiated on every call.
2. **Token field.** Newer OpenAI models want `max_completion_tokens` instead of
   `max_tokens`, while most compatible servers want the opposite. The first 400
   switches to the other one.

Whichever mode is used, the returned text is validated with Pydantic in
app/llm.py; the schema guarantee is never left to the server's goodwill.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Any
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel

from ..config import Settings
from .base import LLMError, Status, strict_json_schema

NAME = "openai"
logger = logging.getLogger(__name__)

#: Schema-enforcement modes, strongest first.
_MODE_CHAIN = ("schema", "object", "prompt")

#: Server capabilities learned during this process. Later calls to the same
#: server do not retry a mode that turned out to be unsupported.
_learned: dict[str, Any] = {"mode": None, "token_param": "max_tokens"}

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "host.docker.internal"}

# Instruction appended to the system prompt in the modes without schema
# enforcement.
_JSON_INSTRUCTION = (
    "Respond with a single JSON object that validates against this JSON Schema. "
    "Output raw JSON only — no prose, no markdown, no code fences.\n\nJSON Schema:\n{schema}"
)


def status(settings: Settings) -> Status:
    if not settings.active_model:
        return Status(
            ready=False,
            detail=(
                "The openai provider requires LLM_MODEL — the valid name depends on "
                "the server (e.g. gpt-4o-mini, deepseek-chat, llama3.1:8b). Add it "
                "to agent/.env."
            ),
        )
    if _needs_key(settings) and not settings.api_key:
        return Status(
            ready=False,
            detail=(
                f"No API key for {_host(settings)}. Add OPENAI_API_KEY=... to "
                "agent/.env (local servers do not need one)."
            ),
        )
    return Status(ready=True, detail=f"{settings.api_base_url} · {settings.active_model}")


async def complete(
    *,
    settings: Settings,
    schema: type[BaseModel],
    system: str,
    prompt: str,
    timeout: float,
) -> str:
    ready = status(settings)
    if not ready.ready:
        raise LLMError(ready.detail)

    last_detail = ""
    for mode in _modes(settings):
        payload = _payload(settings, schema, system, prompt, mode)
        try:
            text = await _post(settings, payload, timeout)
        except _Unsupported as exc:
            # The server does not know this mode: step down and remember it.
            last_detail = str(exc)
            logger.info("json mode '%s' unsupported, stepping down: %s", mode, exc)
            continue
        if _learned["mode"] != mode:
            _learned["mode"] = mode
            logger.info("json mode for this OpenAI-compatible endpoint: %s", mode)
        return text

    raise LLMError(
        "The server accepted none of the JSON modes. Try setting LLM_JSON_MODE "
        f"manually in agent/.env. Last error: {last_detail[:300]}"
    )


def _modes(settings: Settings) -> tuple[str, ...]:
    if settings.llm_json_mode != "auto":
        return (settings.llm_json_mode,)
    learned = _learned["mode"]
    if learned:
        # Start from the learned mode, but still allow stepping further down.
        index = _MODE_CHAIN.index(learned)
        return _MODE_CHAIN[index:]
    return _MODE_CHAIN


def _payload(
    settings: Settings,
    schema: type[BaseModel],
    system: str,
    prompt: str,
    mode: str,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": settings.active_model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    }

    if mode == "schema":
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": schema.__name__,
                "strict": True,
                "schema": strict_json_schema(schema),
            },
        }
        return payload

    instruction = _JSON_INSTRUCTION.format(
        schema=json.dumps(schema.model_json_schema(), ensure_ascii=False)
    )
    payload["messages"][0]["content"] = f"{system}\n\n{instruction}"
    if mode == "object":
        payload["response_format"] = {"type": "json_object"}
    return payload


class _Unsupported(Exception):
    """The server rejected a field in the body — a weaker mode may work."""


async def _post(settings: Settings, payload: dict[str, Any], timeout: float) -> str:
    url = f"{settings.api_base_url}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if settings.api_key:
        headers["Authorization"] = f"Bearer {settings.api_key}"

    for attempt in (1, 2):
        body = dict(payload)
        body[_learned["token_param"]] = settings.llm_max_tokens
        try:
            response = await _http().post(url, json=body, headers=headers, timeout=timeout)
        except httpx.TimeoutException as exc:
            raise LLMError(
                f"The model call did not finish within {timeout:.0f} seconds."
            ) from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"Could not reach {settings.api_base_url}: {exc}") from exc

        if response.status_code == 200:
            return _read_content(response)

        detail = response.text[:600]
        if response.status_code == 400 and attempt == 1 and _is_token_param_error(detail):
            _learned["token_param"] = (
                "max_completion_tokens"
                if _learned["token_param"] == "max_tokens"
                else "max_tokens"
            )
            logger.info("switched token field to '%s'", _learned["token_param"])
            continue
        _raise_http(settings, response.status_code, detail)

    raise LLMError("Unexpected state: retries exhausted.")


def _read_content(response: httpx.Response) -> str:
    try:
        data = response.json()
    except ValueError as exc:
        raise LLMError(f"The server did not return JSON: {response.text[:300]!r}") from exc

    if isinstance(data.get("error"), dict):  # some endpoints return errors with a 200
        raise LLMError(f"The server returned an error: {str(data['error'])[:300]}")

    choices = data.get("choices") or []
    if not choices:
        raise LLMError(f"No 'choices' in the response: {str(data)[:300]}")

    choice = choices[0]
    content = (choice.get("message") or {}).get("content")
    if isinstance(content, list):  # endpoints that return multi-part content
        content = "".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        )

    if choice.get("finish_reason") == "length":
        raise LLMError(
            "The response was cut off at LLM_MAX_TOKENS. Raise that value in "
            "agent/.env or lower SCORE_BATCH_SIZE."
        )
    if not content or not content.strip():
        raise LLMError("The model returned an empty response.")
    return content


def _raise_http(settings: Settings, code: int, detail: str) -> None:
    if code in (401, 403):
        raise LLMError(
            f"{_host(settings)} rejected the credentials ({code}). Check "
            "OPENAI_API_KEY / LLM_API_KEY in agent/.env."
        )
    if code == 404:
        raise LLMError(
            f"Endpoint or model not found ({code}). Check that LLM_BASE_URL ends "
            f"with /v1 and that LLM_MODEL={settings.active_model} is correct."
        )
    if code == 429:
        raise LLMError(
            f"{_host(settings)} hit a rate/quota limit (429). Lower MAX_CONCURRENCY."
        )
    if code == 400 and _is_capability_error(detail):
        raise _Unsupported(detail)
    raise LLMError(f"Server error ({code}): {detail[:300]}")


def _is_token_param_error(detail: str) -> bool:
    lowered = detail.lower()
    return "max_completion_tokens" in lowered or (
        "max_tokens" in lowered and ("unsupported" in lowered or "not supported" in lowered)
    )


def _is_capability_error(detail: str) -> bool:
    lowered = detail.lower()
    return any(
        token in lowered
        for token in ("response_format", "json_schema", "json_object", "schema")
    )


def _needs_key(settings: Settings) -> bool:
    return _host(settings) not in _LOCAL_HOSTS


def _host(settings: Settings) -> str:
    return urlparse(settings.api_base_url).hostname or settings.api_base_url


@lru_cache(maxsize=1)
def _http() -> httpx.AsyncClient:
    """One connection pool per process."""
    return httpx.AsyncClient()
