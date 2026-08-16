"""Anthropic API provider — through the official `anthropic` SDK.

Difference from the claude_cli provider: no Claude Code installation is needed,
but an ANTHROPIC_API_KEY and credit are. This is the way to run in a container
or on a server.

The schema guarantee comes from structured outputs: `messages.parse()` converts
the schema into the shape the SDK expects and validates the response. If the SDK
version does not know that helper, we fall back to raw `output_config.format`.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic import BaseModel

from ..config import Settings
from .base import LLMError, Status, strict_json_schema

NAME = "anthropic"

_MISSING_PACKAGE = (
    "The `anthropic` package is not installed. Install it: "
    "cd agent && ./.venv/bin/pip install anthropic"
)
_MISSING_KEY = (
    "No Anthropic API key. Add ANTHROPIC_API_KEY=sk-ant-... to agent/.env "
    "(get a key at https://console.anthropic.com/settings/keys). If you would "
    "rather not use a key, LLM_PROVIDER=claude_cli uses your Claude Code "
    "subscription instead."
)


def status(settings: Settings) -> Status:
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return Status(ready=False, detail=_MISSING_PACKAGE)
    if not settings.api_key:
        return Status(ready=False, detail=_MISSING_KEY)
    return Status(ready=True, detail="Anthropic API key is set.")


async def complete(
    *,
    settings: Settings,
    schema: type[BaseModel],
    system: str,
    prompt: str,
    timeout: float,
) -> str:
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover - installation problem
        raise LLMError(_MISSING_PACKAGE) from exc

    if not settings.api_key:
        raise LLMError(_MISSING_KEY)

    client = _client(settings.api_key, settings.llm_base_url).with_options(timeout=timeout)
    request: dict[str, Any] = {
        "model": settings.active_model,
        "max_tokens": settings.llm_max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": prompt}],
    }

    parse = getattr(client.messages, "parse", None)
    try:
        if parse is not None:
            response = await parse(output_format=schema, **request)
        else:
            response = await client.messages.create(
                output_config={
                    "format": {"type": "json_schema", "schema": strict_json_schema(schema)}
                },
                **request,
            )
    except Exception as exc:  # noqa: BLE001 - turn SDK exceptions into readable errors
        raise LLMError(_describe(anthropic, exc, settings)) from exc

    _check_stop_reason(response)

    # The parse() path returns a validated model object; the caller expects
    # text, so serialize it back (validation lives only in app/llm.py).
    parsed = getattr(response, "parsed_output", None)
    if parsed is not None:
        return parsed.model_dump_json()

    text = "".join(
        block.text for block in response.content if getattr(block, "type", "") == "text"
    )
    if not text.strip():
        raise LLMError("The Anthropic API returned an empty response.")
    return text


@lru_cache(maxsize=4)
def _client(api_key: str, base_url: str):
    """One client per process — avoids opening a new connection pool per call.

    base_url is optional: point it at an Anthropic-compatible proxy (LiteLLM,
    a corporate gateway) with LLM_BASE_URL if you need to.
    """
    from anthropic import AsyncAnthropic

    return AsyncAnthropic(api_key=api_key, base_url=base_url or None)


def _check_stop_reason(response: Any) -> None:
    reason = getattr(response, "stop_reason", None)
    if reason == "refusal":
        details = getattr(response, "stop_details", None)
        category = getattr(details, "category", None) or "unspecified"
        raise LLMError(
            f"The model refused the request on safety grounds (category: {category})."
        )
    if reason == "max_tokens":
        raise LLMError(
            "The response was cut off at LLM_MAX_TOKENS. Raise that value in "
            "agent/.env or lower SCORE_BATCH_SIZE."
        )


def _describe(anthropic: Any, exc: Exception, settings: Settings) -> str:
    if isinstance(exc, anthropic.AuthenticationError):
        return "Invalid Anthropic API key (401). Check ANTHROPIC_API_KEY."
    if isinstance(exc, anthropic.PermissionDeniedError):
        return (
            "This Anthropic API key has no access to the model (403): "
            f"{settings.active_model}"
        )
    if isinstance(exc, anthropic.NotFoundError):
        return (
            f"Model not found: {settings.active_model}. Check LLM_MODEL in "
            "agent/.env."
        )
    if isinstance(exc, anthropic.RateLimitError):
        return (
            "Hit the Anthropic API rate/quota limit (429). Lower MAX_CONCURRENCY "
            "or wait a moment and retry."
        )
    if isinstance(exc, anthropic.APIConnectionError):
        return "Could not reach the Anthropic API (network error or timeout)."
    if isinstance(exc, anthropic.APIStatusError):
        return f"Anthropic API error ({exc.status_code}): {str(exc)[:300]}"
    return f"Anthropic call failed: {str(exc)[:300]}"
