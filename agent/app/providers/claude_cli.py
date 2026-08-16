"""Claude Code CLI köprüsü — API anahtarı gerektirmeyen sağlayıcı.

Neden SDK değil de CLI: bu yol Claude Pro/Max **üyeliğiyle** çalışıyor, ayrı bir
API anahtarı/kredisi yok. `claude -p` yereldeki Claude Code oturumunun kimliğini
kullanıyor, dolayısıyla ek faturalandırma olmuyor.

Şema garantisi kayboluyor mu: hayır. `--json-schema` bayrağı çıktıyı verdiğimiz
JSON Schema'ya zorluyor, dönen metni ayrıca Pydantic ile doğruluyoruz.

Maliyet yerine **duvar saati** optimize ediliyor: üyelikte token başına ücret
yok ama her çağrı ayrı bir subprocess ve ~16k token sabit ek yük taşıyor.
Bu yüzden partiler küçük tutulup paralel çalıştırılıyor (bkz. match/scorer.py).
"""

from __future__ import annotations

import asyncio
import json
import shutil

from pydantic import BaseModel

from ..config import Settings
from .base import LLMError, Status

NAME = "claude_cli"

#: Bu bir tamamlama çağrısı, ajan oturumu değil — araçları kapatıyoruz ki
#: model dosya okumaya/web'de aramaya kalkışmasın ve çıktı deterministik olsun.
_DISALLOWED_TOOLS = (
    "Bash,Read,Write,Edit,Glob,Grep,WebSearch,WebFetch,Task,TodoWrite,NotebookEdit"
)


def status(settings: Settings) -> Status:
    if shutil.which(settings.claude_cli) is None:
        return Status(
            ready=False,
            detail=(
                f"'{settings.claude_cli}' komutu bulunamadı. Claude Code kurulu ve "
                "PATH üzerinde olmalı (kontrol: `claude --version`). Claude Code "
                "kullanmak istemiyorsan agent/.env içinde LLM_PROVIDER değerini "
                "'anthropic' ya da 'openai' yap."
            ),
        )
    return Status(ready=True, detail="Claude Code CLI bulundu (üyelik oturumu kullanılıyor).")


async def complete(
    *,
    settings: Settings,
    schema: type[BaseModel],
    system: str,
    prompt: str,
    timeout: float,
) -> str:
    """Prompt stdin'den geçiriliyor: ilan partileri onbinlerce karakter olabiliyor
    ve argüman listesi sınırına takılmak istemiyoruz.
    """
    cli = shutil.which(settings.claude_cli)
    if cli is None:
        raise LLMError(status(settings).detail)

    cmd = [
        cli,
        "-p",
        "--output-format", "json",
        "--json-schema", json.dumps(schema.model_json_schema()),
        "--system-prompt", system,
        "--model", settings.active_model,
        "--max-turns", "1",
        "--disallowed-tools", _DISALLOWED_TOOLS,
    ]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        # Depoda çalıştırmıyoruz: proje CLAUDE.md'si ve dosyaları çağrıya
        # sızmasın, çıktı çalışma dizininden bağımsız olsun.
        cwd=settings.cli_workdir,
    )

    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(prompt.encode("utf-8")),
            timeout=timeout,
        )
    except asyncio.TimeoutError as exc:
        process.kill()
        await process.wait()
        raise LLMError(
            f"Model çağrısı {timeout:.0f} saniyede tamamlanmadı."
        ) from exc

    if process.returncode != 0:
        detail = (stderr or stdout).decode("utf-8", errors="replace").strip()
        raise LLMError(f"claude çıkış kodu {process.returncode}: {detail[:400]}")

    try:
        envelope = json.loads(stdout.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        raise LLMError(f"claude çıktısı JSON değil: {stdout[:300]!r}") from exc

    if envelope.get("is_error"):
        raise LLMError(f"claude hata döndürdü: {str(envelope.get('result'))[:400]}")

    result = envelope.get("result")
    if not isinstance(result, str) or not result.strip():
        raise LLMError("claude boş yanıt döndürdü.")
    return result
