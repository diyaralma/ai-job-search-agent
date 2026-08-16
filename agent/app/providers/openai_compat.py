"""OpenAI ve OpenAI-uyumlu her uç için sağlayıcı.

Tek bir `POST {base_url}/chat/completions` çağrısı olduğu için resmî SDK yerine
projede zaten kullanılan httpx tercih edildi: OpenRouter, Groq, Together,
DeepSeek, Ollama, LM Studio, vLLM gibi uçların hepsi bu sözleşmeyi konuşuyor
ama parametre desteğinde ayrışıyorlar. Gövdeyi kendimiz kurunca desteklenmeyen
bir alanı görüp geri adım atabiliyoruz.

Ayrıştığı iki nokta ve ele alınışı:

1. **Şema zorlaması.** OpenAI `response_format.json_schema` destekliyor, çoğu
   yerel sunucu desteklemiyor. LLM_JSON_MODE=auto en güçlüsünden başlar,
   400 alınca `json_object`a, o da yoksa şemayı sisteme yazıp serbest metne
   düşer. Çalışan kip hatırlanır — her çağrıda baştan denenmez.
2. **Token alanı.** Yeni OpenAI modelleri `max_tokens` yerine
   `max_completion_tokens` istiyor, uyumlu sunucuların çoğu tersi. İlk 400'de
   diğerine geçilir.

Hangi kip kullanılırsa kullanılsın dönen metin app/llm.py'de Pydantic ile
doğrulanıyor; şema garantisi sunucunun insafına bırakılmıyor.
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

#: Güçlüden zayıfa şema zorlama kipleri.
_MODE_CHAIN = ("schema", "object", "prompt")

#: Süreç boyunca öğrenilen sunucu yetenekleri. Aynı sunucuya yapılan sonraki
#: çağrılar desteklenmediği anlaşılan kipi tekrar denemez.
_learned: dict[str, Any] = {"mode": None, "token_param": "max_tokens"}

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "host.docker.internal"}

# Şema zorlaması olmayan kiplerde sisteme eklenen talimat. İngilizce: küçük
# yerel modeller biçim talimatlarını İngilizce daha güvenilir izliyor.
_JSON_INSTRUCTION = (
    "Respond with a single JSON object that validates against this JSON Schema. "
    "Output raw JSON only — no prose, no markdown, no code fences.\n\nJSON Schema:\n{schema}"
)


def status(settings: Settings) -> Status:
    if not settings.active_model:
        return Status(
            ready=False,
            detail=(
                "openai sağlayıcısı için LLM_MODEL zorunlu — sunucuya göre değişiyor "
                "(ör. gpt-4o-mini, deepseek-chat, llama3.1:8b). agent/.env içine ekle."
            ),
        )
    if _needs_key(settings) and not settings.api_key:
        return Status(
            ready=False,
            detail=(
                f"{_host(settings)} için API anahtarı yok. agent/.env içine "
                "OPENAI_API_KEY=... ekle (yerel sunucularda gerekmez)."
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
            # Sunucu bu kipi tanımıyor: bir alt kipe düş ve öğrendiğimizi sakla.
            last_detail = str(exc)
            logger.info("json kipi '%s' desteklenmiyor, düşülüyor: %s", mode, exc)
            continue
        if _learned["mode"] != mode:
            _learned["mode"] = mode
            logger.info("OpenAI-uyumlu uç için json kipi: %s", mode)
        return text

    raise LLMError(
        "Sunucu hiçbir JSON kipini kabul etmedi. agent/.env içinde "
        f"LLM_JSON_MODE değerini elle ayarlamayı dene. Son hata: {last_detail[:300]}"
    )


def _modes(settings: Settings) -> tuple[str, ...]:
    if settings.llm_json_mode != "auto":
        return (settings.llm_json_mode,)
    learned = _learned["mode"]
    if learned:
        # Öğrenilen kipten başla, gerekirse yine aşağı düşebil.
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
    """Sunucu gövdedeki bir alanı tanımadı — daha zayıf bir kiple denenebilir."""


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
            raise LLMError(f"Model çağrısı {timeout:.0f} saniyede tamamlanmadı.") from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"{settings.api_base_url} adresine bağlanılamadı: {exc}") from exc

        if response.status_code == 200:
            return _read_content(response)

        detail = response.text[:600]
        if response.status_code == 400 and attempt == 1 and _is_token_param_error(detail):
            _learned["token_param"] = (
                "max_completion_tokens"
                if _learned["token_param"] == "max_tokens"
                else "max_tokens"
            )
            logger.info("token alanı '%s' olarak değiştirildi", _learned["token_param"])
            continue
        _raise_http(settings, response.status_code, detail)

    raise LLMError("Beklenmeyen durum: istek tekrarları tükendi.")


def _read_content(response: httpx.Response) -> str:
    try:
        data = response.json()
    except ValueError as exc:
        raise LLMError(f"Sunucu JSON döndürmedi: {response.text[:300]!r}") from exc

    if isinstance(data.get("error"), dict):  # bazı uçlar hatayı 200 ile döndürüyor
        raise LLMError(f"Sunucu hata döndürdü: {str(data['error'])[:300]}")

    choices = data.get("choices") or []
    if not choices:
        raise LLMError(f"Yanıtta 'choices' yok: {str(data)[:300]}")

    choice = choices[0]
    content = (choice.get("message") or {}).get("content")
    if isinstance(content, list):  # çok parçalı içerik döndüren uçlar
        content = "".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        )

    if choice.get("finish_reason") == "length":
        raise LLMError(
            "Yanıt LLM_MAX_TOKENS sınırında kesildi. agent/.env içindeki değeri "
            "artır ya da SCORE_BATCH_SIZE'ı küçült."
        )
    if not content or not content.strip():
        raise LLMError("Model boş yanıt döndürdü.")
    return content


def _raise_http(settings: Settings, code: int, detail: str) -> None:
    if code in (401, 403):
        raise LLMError(
            f"{_host(settings)} kimlik doğrulamayı reddetti ({code}). "
            "agent/.env içindeki OPENAI_API_KEY / LLM_API_KEY değerini kontrol et."
        )
    if code == 404:
        raise LLMError(
            f"Uç ya da model bulunamadı ({code}). LLM_BASE_URL sonuna /v1 eklemeyi "
            f"ve LLM_MODEL={settings.active_model} değerinin doğruluğunu kontrol et."
        )
    if code == 429:
        raise LLMError(
            f"{_host(settings)} hız/kota sınırına takıldı (429). MAX_CONCURRENCY'yi düşür."
        )
    if code == 400 and _is_capability_error(detail):
        raise _Unsupported(detail)
    raise LLMError(f"Sunucu hatası ({code}): {detail[:300]}")


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
    """Süreç başına tek bağlantı havuzu."""
    return httpx.AsyncClient()
