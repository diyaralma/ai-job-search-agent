"""Claude Code CLI bridge — the provider that needs no API key.

Why the CLI and not the SDK: this path runs on a Claude Pro/Max **subscription**,
with no separate API key or credit. `claude -p` uses the local Claude Code
session's identity, so there is no extra billing.

Does that lose the schema guarantee? No. The `--json-schema` flag forces the
output to the JSON Schema we pass, and the returned text is additionally
validated with Pydantic.

**Wall-clock** is optimized instead of cost: a subscription has no per-token
charge, but every call is a separate subprocess carrying ~16k tokens of fixed
overhead. Hence small batches run in parallel (see match/scorer.py).
"""

from __future__ import annotations

import asyncio
import json
import shutil

from pydantic import BaseModel

from ..config import Settings
from .base import LLMError, Status

NAME = "claude_cli"

#: This is a completion call, not an agent session — tools are disabled so the
#: model cannot read files or search the web and the output stays deterministic.
_DISALLOWED_TOOLS = (
    "Bash,Read,Write,Edit,Glob,Grep,WebSearch,WebFetch,Task,TodoWrite,NotebookEdit"
)


def status(settings: Settings) -> Status:
    if shutil.which(settings.claude_cli) is None:
        return Status(
            ready=False,
            detail=(
                f"Command '{settings.claude_cli}' not found. Claude Code must be "
                "installed and on PATH (check: `claude --version`). If you would "
                "rather not use Claude Code, set LLM_PROVIDER to 'anthropic' or "
                "'openai' in agent/.env."
            ),
        )
    return Status(ready=True, detail="Claude Code CLI found (using your subscription session).")


async def complete(
    *,
    settings: Settings,
    schema: type[BaseModel],
    system: str,
    prompt: str,
    timeout: float,
) -> str:
    """The prompt goes through stdin: posting batches can be tens of thousands of
    characters and we do not want to hit the argument-list limit.
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
        # Not run inside the repo: the project's CLAUDE.md and files must not
        # leak into the call, and output must not depend on the working dir.
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
            f"The model call did not finish within {timeout:.0f} seconds."
        ) from exc

    if process.returncode != 0:
        detail = (stderr or stdout).decode("utf-8", errors="replace").strip()
        raise LLMError(f"claude exited with {process.returncode}: {detail[:400]}")

    try:
        envelope = json.loads(stdout.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        raise LLMError(f"claude output was not JSON: {stdout[:300]!r}") from exc

    if envelope.get("is_error"):
        raise LLMError(f"claude returned an error: {str(envelope.get('result'))[:400]}")

    result = envelope.get("result")
    if not isinstance(result, str) or not result.strip():
        raise LLMError("claude returned an empty response.")
    return result
