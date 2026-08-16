"""Shared contract and helpers for provider modules.

Every provider module exposes two things:

    status(settings) -> Status          usable without making a call?
    async complete(...) -> str          the JSON text the model produced

Providers do not validate: the returned text is validated in one place
(app/llm.py) with Pydantic, so a "schema mismatch" error looks the same on
every provider.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel


class LLMError(RuntimeError):
    """A model call could not be completed."""


@dataclass(frozen=True)
class Status:
    """Provider readiness that can be determined without making a call."""

    ready: bool
    detail: str


# JSON Schema keywords some providers (notably OpenAI strict mode) reject or
# ignore.
_DROPPED_KEYWORDS = {"default", "title", "examples", "$comment"}


def strict_json_schema(schema: type[BaseModel]) -> dict[str, Any]:
    """Adapts a Pydantic schema to "strict" structured-output rules.

    The rules are common across providers: every object needs
    `additionalProperties: false` and must list all of its fields in `required`.
    Pydantic emits neither by itself.
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
    """Pulls the JSON body out of a model response.

    With providers that cannot enforce a schema (local models, endpoints without
    json_schema support) the answer may arrive wrapped in a ```json fence or a
    short sentence. Text that is already valid JSON is returned untouched.
    """
    candidate = text.strip()
    if _looks_like_json(candidate):
        return candidate

    stripped = _FENCE.sub("", candidate).strip()
    if _looks_like_json(stripped):
        return stripped

    # Last resort: the outermost { … } block in the text
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
