"""Minimal .env reader/writer for settings the UI can change at runtime.

Only optional job-source credentials go through here (see main.py). The point is
that a user should not have to edit a file and restart the service just to add a
free Jooble key — the app is a local single-user tool, so persisting to
`agent/.env` is both the simplest and the least surprising place.

Comments, ordering and unrelated keys in the file are preserved: an existing
`KEY=` line is replaced in place, a new one is appended.
"""

from __future__ import annotations

from pathlib import Path

#: agent/.env — resolved from this file, not the working directory, so it lands
#: in the same place regardless of where the service was started from.
ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
EXAMPLE_PATH = ENV_PATH.with_name(".env.example")


def update(values: dict[str, str]) -> None:
    """Writes the given key/value pairs into agent/.env."""
    lines = _current_lines()

    for key, value in values.items():
        replacement = f"{key}={value}"
        for index, line in enumerate(lines):
            if line.strip().startswith(f"{key}="):
                lines[index] = replacement
                break
        else:
            lines.append(replacement)

    ENV_PATH.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8")


def _current_lines() -> list[str]:
    if ENV_PATH.exists():
        return ENV_PATH.read_text(encoding="utf-8").splitlines()
    if EXAMPLE_PATH.exists():
        return EXAMPLE_PATH.read_text(encoding="utf-8").splitlines()
    return []
