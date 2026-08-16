"""Seçili LLM sağlayıcısını tek ucuz çağrıyla doğrular.

CV yüklemeden önce çalıştır: anahtar eksikse, model adı yanlışsa ya da oturum
düşmüşse buradan net bir hata alırsın — 30 saniyelik CV analizinin sonunda değil.

    ./.venv/bin/python scripts/check_llm.py
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic import BaseModel, Field  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.llm import LLMError, provider_status, structured  # noqa: E402


class Ping(BaseModel):
    ok: bool = Field(description="Her zaman true döndür")
    note: str = Field(description="Tek kelimeyle 'hazir' yaz")


HINTS = {
    "claude_cli": [
        "Claude Code oturumu düşmüş olabilir (`claude` komutunu çalıştırıp giriş yap)",
        "Üyelik kullanım limitine ulaşılmış olabilir",
        "LLM_MODEL ayarındaki modele erişimin olmayabilir",
    ],
    "anthropic": [
        "ANTHROPIC_API_KEY geçersiz ya da kredisi bitmiş olabilir",
        "LLM_MODEL adı yanlış olabilir (ör. claude-opus-5, claude-sonnet-5)",
        "`anthropic` paketi kurulu olmayabilir: ./.venv/bin/pip install anthropic",
    ],
    "openai": [
        "LLM_BASE_URL yanlış olabilir — çoğu uçta sonunda /v1 olmalı",
        "LLM_MODEL sunucuda yüklü olmayabilir (yerel sunucularda `ollama list` vb.)",
        "API anahtarı eksik ya da geçersiz olabilir",
        "Sunucu JSON şeması desteklemiyorsa LLM_JSON_MODE=object ya da prompt dene",
    ],
}


async def main() -> int:
    settings = get_settings()
    status = provider_status()

    print(f"sağlayıcı : {settings.llm_provider}")
    print(f"model     : {settings.active_model or '(tanımsız)'}")
    if settings.llm_provider == "openai":
        print(f"uç        : {settings.api_base_url}")
    print(f"durum     : {status.detail}")

    if not status.ready:
        print("\nBAŞARISIZ: sağlayıcı hazır değil (yukarıdaki durum satırına bak).")
        return 1

    print("çağrı yapılıyor…")
    started = time.perf_counter()
    try:
        result = await structured(
            schema=Ping,
            system="Sen bir sağlık kontrolü uç noktasısın. Yalnızca istenen JSON'u üret.",
            prompt="ping",
            timeout=120,
        )
    except LLMError as exc:
        print(f"\nBAŞARISIZ: {exc}")
        print("\nOlası nedenler:")
        for hint in HINTS.get(settings.llm_provider, []):
            print(f"  - {hint}")
        return 1

    elapsed = time.perf_counter() - started
    print(f"\nBAŞARILI: {result.note} (ok={result.ok}) — {elapsed:.1f} sn")
    print("CV yükleyip arama yapabilirsin.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
