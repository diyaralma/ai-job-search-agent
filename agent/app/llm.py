"""Structured model calls — one provider-agnostic entry point.

Which model gets used is chosen with `LLM_PROVIDER` in `agent/.env`:

    claude_cli  Claude Code CLI (`claude -p`). No API key; uses the local
                Claude Pro/Max subscription session. Default.
    anthropic   Anthropic API. Requires ANTHROPIC_API_KEY.
    openai      OpenAI and any OpenAI-compatible endpoint: OpenRouter, Groq,
                Together, DeepSeek, Google's OpenAI endpoint, Ollama, LM Studio,
                vLLM… Configured with LLM_BASE_URL + LLM_MODEL.

The pipeline knows nothing about providers: every step just calls `structured()`.

The schema guarantee is provider-independent. Each provider uses the strongest
tool it has (`--json-schema` on the CLI, structured outputs on the Anthropic API,
`response_format` on OpenAI-compatible endpoints) and the returned text is
**always** validated here with Pydantic. If a weak local model cannot hold the
schema, the error is explicit instead of silently corrupt data.
"""

from __future__ import annotations

import logging
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from .config import Settings, get_settings
from .providers import REGISTRY
from .providers.base import LLMError, Status, extract_json

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

__all__ = ["LLMError", "structured", "provider_status", "describe_provider"]


def _provider(settings: Settings):
    try:
        return REGISTRY[settings.llm_provider]
    except KeyError as exc:
        raise LLMError(
            f"Unknown LLM_PROVIDER: {settings.llm_provider!r}. "
            f"Valid values: {', '.join(REGISTRY)}"
        ) from exc


def provider_status() -> Status:
    """Reports whether the provider is usable without making a call.

    Used by the UI and start.sh: the user should see "no API key" upfront, not
    at the end of a 30-second CV analysis.
    """
    settings = get_settings()
    try:
        return _provider(settings).status(settings)
    except LLMError as exc:
        return Status(ready=False, detail=str(exc))


def describe_provider() -> dict:
    """Summary returned by the health endpoint (contains no secrets)."""
    settings = get_settings()
    status = provider_status()
    return {
        "provider": settings.llm_provider,
        "model": settings.active_model or "(unset)",
        "ready": status.ready,
        "detail": status.detail,
    }


async def structured(
    *,
    schema: type[T],
    system: str,
    prompt: str,
    timeout: float | None = None,
) -> T:
    """Produces a single response conforming to the schema."""
    settings = get_settings()
    provider = _provider(settings)

    raw = await provider.complete(
        settings=settings,
        schema=schema,
        system=system,
        prompt=prompt,
        timeout=timeout or settings.request_timeout,
    )

    try:
        return schema.model_validate_json(extract_json(raw))
    except ValidationError as exc:
        logger.warning(
            "Schema validation failed (%s/%s): %s",
            settings.llm_provider,
            settings.active_model,
            str(exc)[:300],
        )
        raise LLMError(
            f"Model output did not match the schema ({settings.active_model}): {str(exc)[:300]}"
        ) from exc
