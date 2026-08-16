"""Verifies the selected LLM provider with a single cheap call.

Run it before uploading a CV: if a key is missing, the model name is wrong or
the session expired, you get a clear error here rather than at the end of a
30-second CV analysis.

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
    ok: bool = Field(description="Always return true")
    note: str = Field(description="Write the single word 'ready'")


HINTS = {
    "claude_cli": [
        "The Claude Code session may have expired (run `claude` and log in)",
        "You may have hit your subscription usage limit",
        "You may not have access to the model in LLM_MODEL",
    ],
    "anthropic": [
        "ANTHROPIC_API_KEY may be invalid or out of credit",
        "LLM_MODEL may be wrong (e.g. claude-opus-5, claude-sonnet-5)",
        "The `anthropic` package may not be installed: ./.venv/bin/pip install anthropic",
    ],
    "openai": [
        "LLM_BASE_URL may be wrong — most endpoints need a trailing /v1",
        "LLM_MODEL may not be loaded on the server (`ollama list` and friends)",
        "The API key may be missing or invalid",
        "If the server has no schema support, try LLM_JSON_MODE=object or prompt",
    ],
}


async def main() -> int:
    settings = get_settings()
    status = provider_status()

    print(f"provider : {settings.llm_provider}")
    print(f"model    : {settings.active_model or '(unset)'}")
    if settings.llm_provider == "openai":
        print(f"endpoint : {settings.api_base_url}")
    print(f"status   : {status.detail}")

    if not status.ready:
        print("\nFAILED: provider not ready (see the status line above).")
        return 1

    print("calling…")
    started = time.perf_counter()
    try:
        result = await structured(
            schema=Ping,
            system="You are a health-check endpoint. Produce only the requested JSON.",
            prompt="ping",
            timeout=120,
        )
    except LLMError as exc:
        print(f"\nFAILED: {exc}")
        print("\nPossible causes:")
        for hint in HINTS.get(settings.llm_provider, []):
            print(f"  - {hint}")
        return 1

    elapsed = time.perf_counter() - started
    print(f"\nOK: {result.note} (ok={result.ok}) — {elapsed:.1f}s")
    print("You can upload a CV and run a search.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
