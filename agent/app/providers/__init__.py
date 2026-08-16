"""Model providers.

To add one: write a module that implements the contract in base.py (status +
complete) and add it to the table below. The caller (app/llm.py) and the
pipeline stay unchanged.
"""

from . import anthropic_api, claude_cli, openai_compat
from .base import LLMError, Status

#: LLM_PROVIDER value -> provider module
REGISTRY = {
    claude_cli.NAME: claude_cli,
    anthropic_api.NAME: anthropic_api,
    openai_compat.NAME: openai_compat,
}

__all__ = ["REGISTRY", "LLMError", "Status"]
