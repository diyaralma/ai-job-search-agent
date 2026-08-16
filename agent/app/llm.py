"""Yapılandırılmış model çağrıları — sağlayıcıdan bağımsız tek giriş noktası.

Hangi modelin kullanılacağı `agent/.env` içindeki `LLM_PROVIDER` ile seçilir:

    claude_cli  Claude Code CLI (`claude -p`). API anahtarı yok; yereldeki
                Claude Pro/Max üyelik oturumunu kullanır. Varsayılan.
    anthropic   Anthropic API. ANTHROPIC_API_KEY gerekir.
    openai      OpenAI ve OpenAI-uyumlu her uç: OpenRouter, Groq, Together,
                DeepSeek, Google'ın OpenAI uçu, Ollama, LM Studio, vLLM…
                LLM_BASE_URL + LLM_MODEL ile ayarlanır.

Pipeline sağlayıcıyı bilmez: her adım yalnızca `structured()` çağırır.

Şema garantisi sağlayıcıdan bağımsız: her biri elindeki en güçlü aracı kullanır
(CLI'da `--json-schema`, Anthropic'te structured outputs, OpenAI-uyumlu uçlarda
`response_format`), dönen metni **her hâlükârda** burada Pydantic ile
doğrularız. Zayıf bir yerel model şemayı tutturamazsa hata net olur.
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
            f"Bilinmeyen LLM_PROVIDER: {settings.llm_provider!r}. "
            f"Geçerli değerler: {', '.join(REGISTRY)}"
        ) from exc


def provider_status() -> Status:
    """Çağrı yapmadan sağlayıcının hazır olup olmadığını söyler.

    Arayüz ve start.sh bunu kullanıyor: kullanıcı 30 saniyelik CV analizinin
    sonunda değil, en başta "anahtar tanımlı değil" uyarısını görsün.
    """
    settings = get_settings()
    try:
        return _provider(settings).status(settings)
    except LLMError as exc:
        return Status(ready=False, detail=str(exc))


def describe_provider() -> dict:
    """Sağlık uç noktasının döndürdüğü özet (sır içermez)."""
    settings = get_settings()
    status = provider_status()
    return {
        "provider": settings.llm_provider,
        "model": settings.active_model or "(tanımsız)",
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
    """Şemaya uyan tek bir yanıt üretir."""
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
            "Şema doğrulaması başarısız (%s/%s): %s",
            settings.llm_provider,
            settings.active_model,
            str(exc)[:300],
        )
        raise LLMError(
            f"Model çıktısı şemaya uymadı ({settings.active_model}): {str(exc)[:300]}"
        ) from exc
