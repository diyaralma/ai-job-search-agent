"""Anthropic API sağlayıcısı — resmî `anthropic` SDK'sı üzerinden.

claude_cli sağlayıcısından farkı: Claude Code kurulumu gerekmez, karşılığında
ANTHROPIC_API_KEY ve kredi gerekir. Konteynerde/sunucuda çalıştırmanın yolu bu.

Şema garantisi structured outputs ile sağlanıyor: `messages.parse()` şemayı
SDK'nın kabul ettiği biçime çevirip yanıtı doğruluyor. SDK sürümü bu yardımcıyı
tanımıyorsa ham `output_config.format` yoluna düşüyoruz.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic import BaseModel

from ..config import Settings
from .base import LLMError, Status, strict_json_schema

NAME = "anthropic"

_MISSING_PACKAGE = (
    "`anthropic` paketi kurulu değil. Kur: "
    "cd agent && ./.venv/bin/pip install anthropic"
)
_MISSING_KEY = (
    "Anthropic API anahtarı yok. agent/.env içine ANTHROPIC_API_KEY=sk-ant-... "
    "ekle (anahtar: https://console.anthropic.com/settings/keys). Anahtar "
    "istemiyorsan LLM_PROVIDER=claude_cli ile Claude Code üyeliğini kullanabilirsin."
)


def status(settings: Settings) -> Status:
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return Status(ready=False, detail=_MISSING_PACKAGE)
    if not settings.api_key:
        return Status(ready=False, detail=_MISSING_KEY)
    return Status(ready=True, detail="Anthropic API anahtarı tanımlı.")


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
    except ImportError as exc:  # pragma: no cover - kurulum hatası
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
    except Exception as exc:  # noqa: BLE001 - SDK istisnalarını Türkçeleştiriyoruz
        raise LLMError(_describe(anthropic, exc, settings)) from exc

    _check_stop_reason(response)

    # parse() yolunda doğrulanmış model nesnesi geliyor; üst katman metin
    # beklediği için tekrar JSON'a çeviriyoruz (tek doğrulama noktası app/llm.py).
    parsed = getattr(response, "parsed_output", None)
    if parsed is not None:
        return parsed.model_dump_json()

    text = "".join(
        block.text for block in response.content if getattr(block, "type", "") == "text"
    )
    if not text.strip():
        raise LLMError("Anthropic API boş yanıt döndürdü.")
    return text


@lru_cache(maxsize=4)
def _client(api_key: str, base_url: str):
    """Süreç başına tek istemci — her çağrıda yeni bağlantı havuzu açmamak için.

    base_url isteğe bağlı: Anthropic-uyumlu bir vekil (LiteLLM, kurumsal proxy)
    arkasındaysan LLM_BASE_URL ile yönlendirebilirsin.
    """
    from anthropic import AsyncAnthropic

    return AsyncAnthropic(api_key=api_key, base_url=base_url or None)


def _check_stop_reason(response: Any) -> None:
    reason = getattr(response, "stop_reason", None)
    if reason == "refusal":
        details = getattr(response, "stop_details", None)
        category = getattr(details, "category", None) or "belirtilmemiş"
        raise LLMError(
            f"Model isteği güvenlik gerekçesiyle reddetti (kategori: {category})."
        )
    if reason == "max_tokens":
        raise LLMError(
            "Yanıt LLM_MAX_TOKENS sınırında kesildi. agent/.env içindeki değeri "
            "artır ya da SCORE_BATCH_SIZE'ı küçült."
        )


def _describe(anthropic: Any, exc: Exception, settings: Settings) -> str:
    if isinstance(exc, anthropic.AuthenticationError):
        return "Anthropic API anahtarı geçersiz (401). ANTHROPIC_API_KEY değerini kontrol et."
    if isinstance(exc, anthropic.PermissionDeniedError):
        return (
            "Anthropic API anahtarının bu modele erişimi yok (403): "
            f"{settings.active_model}"
        )
    if isinstance(exc, anthropic.NotFoundError):
        return (
            f"Model bulunamadı: {settings.active_model}. agent/.env içindeki "
            "LLM_MODEL değerini kontrol et."
        )
    if isinstance(exc, anthropic.RateLimitError):
        return (
            "Anthropic API hız/kota sınırına takıldı (429). MAX_CONCURRENCY'yi "
            "düşür ya da biraz bekleyip tekrar dene."
        )
    if isinstance(exc, anthropic.APIConnectionError):
        return "Anthropic API'ye bağlanılamadı (ağ hatası ya da zaman aşımı)."
    if isinstance(exc, anthropic.APIStatusError):
        return f"Anthropic API hatası ({exc.status_code}): {str(exc)[:300]}"
    return f"Anthropic çağrısı başarısız: {str(exc)[:300]}"
