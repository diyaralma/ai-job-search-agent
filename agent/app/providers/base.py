"""Sağlayıcı modüllerinin ortak sözleşmesi ve yardımcıları.

Her sağlayıcı modülü iki şey sunar:

    status(settings) -> Status          çağrı yapmadan hazır mı?
    async complete(...) -> str          modelin ürettiği JSON metni

Doğrulamayı sağlayıcılar yapmaz: dönen metni tek yerde (app/llm.py) Pydantic
ile doğruluyoruz. Böylece "şema tutmadı" hatası her sağlayıcıda aynı görünüyor.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel


class LLMError(RuntimeError):
    """Model çağrısı tamamlanamadı."""


@dataclass(frozen=True)
class Status:
    """Sağlayıcının çağrı yapmadan anlaşılabilen hazırlık durumu."""

    ready: bool
    detail: str


# JSON Schema'da bazı sağlayıcıların (özellikle OpenAI strict kipi) kabul
# etmediği ya da yok saydığı anahtarlar.
_DROPPED_KEYWORDS = {"default", "title", "examples", "$comment"}


def strict_json_schema(schema: type[BaseModel]) -> dict[str, Any]:
    """Pydantic şemasını 'strict' structured-output kurallarına uydurur.

    Kurallar sağlayıcılar arasında ortak: her nesne `additionalProperties:
    false` olmalı ve tüm alanları `required` listesinde bulunmalı. Pydantic
    ikisini de kendiliğinden üretmiyor.
    """
    return _strictify(schema.model_json_schema())


def _strictify(node: Any) -> Any:
    if isinstance(node, list):
        return [_strictify(item) for item in node]
    if not isinstance(node, dict):
        return node

    out = {k: _strictify(v) for k, v in node.items() if k not in _DROPPED_KEYWORDS}
    if out.get("type") == "object" or "properties" in out:
        out["additionalProperties"] = False
        out["required"] = list(out.get("properties", {}))
    return out


_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


def extract_json(text: str) -> str:
    """Model yanıtından JSON gövdesini ayıklar.

    Şema zorlaması olmayan sağlayıcılarda (yerel modeller, json_schema
    desteklemeyen uçlar) yanıt ```json çitiyle ya da kısa bir cümleyle sarılı
    gelebiliyor. Doğrudan geçerliyse dokunmuyoruz.
    """
    candidate = text.strip()
    if _looks_like_json(candidate):
        return candidate

    stripped = _FENCE.sub("", candidate).strip()
    if _looks_like_json(stripped):
        return stripped

    # Son çare: metindeki en dıştaki { … } bloğu
    start, end = stripped.find("{"), stripped.rfind("}")
    if start != -1 and end > start:
        block = stripped[start : end + 1]
        if _looks_like_json(block):
            return block
    return candidate


def _looks_like_json(text: str) -> bool:
    try:
        json.loads(text)
    except (ValueError, TypeError):
        return False
    return True
