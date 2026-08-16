"""Model sağlayıcıları.

Yeni bir sağlayıcı eklemek: base.py'deki sözleşmeyi (status + complete) sunan
bir modül yaz ve aşağıdaki tabloya ekle. Çağrı yapan taraf (app/llm.py) ve
pipeline değişmez.
"""

from . import anthropic_api, claude_cli, openai_compat
from .base import LLMError, Status

#: LLM_PROVIDER değeri → sağlayıcı modülü
REGISTRY = {
    claude_cli.NAME: claude_cli,
    anthropic_api.NAME: anthropic_api,
    openai_compat.NAME: openai_compat,
}

__all__ = ["REGISTRY", "LLMError", "Status"]
