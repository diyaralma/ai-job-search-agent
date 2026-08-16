import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

LLMProvider = Literal["claude_cli", "anthropic", "openai"]

#: Default model per provider.
#:
#: "openai" is deliberately empty: on OpenAI-compatible endpoints (OpenRouter,
#: Groq, Ollama, LM Studio, vLLM…) the valid model name depends on the server.
#: Guessing one only leads the user into a "model not found" error, so we
#: require LLM_MODEL instead and fail with a clear message.
DEFAULT_MODELS: dict[str, str] = {
    "claude_cli": "claude-opus-5",
    "anthropic": "claude-opus-5",
    "openai": "",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # -- Model access -------------------------------------------------------
    # Three providers: see app/llm.py
    #   claude_cli  Claude Code CLI (`claude -p`) — no API key, uses your session
    #   anthropic   Anthropic API — ANTHROPIC_API_KEY
    #   openai      OpenAI and any OpenAI-compatible endpoint (via LLM_BASE_URL)
    llm_provider: LLMProvider = "claude_cli"
    llm_model: str = ""          # empty -> DEFAULT_MODELS
    llm_api_key: str = ""        # empty -> ANTHROPIC_API_KEY / OPENAI_API_KEY
    llm_base_url: str = ""       # openai provider (and optional Anthropic proxy)
    llm_timeout: float = 300.0
    llm_max_tokens: int = 16000
    # Not every OpenAI-compatible server supports json_schema (local models
    # usually do not). "auto" starts with the strongest mode, steps down on
    # error and remembers what worked.
    llm_json_mode: Literal["auto", "schema", "object", "prompt"] = "auto"

    # Standard names — the user may already have these in their environment
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    # claude_cli provider only
    claude_cli: str = "claude"

    # Backwards compatibility with older .env files
    agent_model: str = ""
    claude_timeout: float | None = None

    # -- Optional job sources ----------------------------------------------
    adzuna_app_id: str | None = None
    adzuna_app_key: str | None = None
    jooble_api_key: str | None = None
    # Jooble keys are REGIONAL: a jooble.org key queries the US index. For
    # Turkish postings, get the key from tr.jooble.org and set this to
    # https://tr.jooble.org
    jooble_host: str = "https://jooble.org"

    # -- Application --------------------------------------------------------
    db_path: str = "./data/jobsearch.db"
    cors_origins: str = "http://localhost:3001,http://localhost:3000"

    # The cost model depends on the provider: with a Claude Code subscription
    # there is no per-token charge (optimize wall-clock — small batches, high
    # parallelism), while API providers bill every call. The defaults are picked
    # to finish in a single wave (32 / 8 = 4 batches, 4 concurrent); on a paid
    # provider, lowering LLM_SCORE_LIMIT is a direct saving.
    llm_score_limit: int = 32
    score_batch_size: int = 8
    max_concurrency: int = 4

    fetch_limit_per_source: int = 120
    http_timeout: float = 25.0

    # -- Derived values -----------------------------------------------------
    @property
    def active_model(self) -> str:
        """Model name used for calls (legacy AGENT_MODEL is still honoured)."""
        return self.llm_model or self.agent_model or DEFAULT_MODELS[self.llm_provider]

    @property
    def request_timeout(self) -> float:
        return self.claude_timeout if self.claude_timeout is not None else self.llm_timeout

    @property
    def api_key(self) -> str:
        """Key for the selected provider; meaningless for claude_cli (returns "")."""
        if self.llm_api_key:
            return self.llm_api_key
        if self.llm_provider == "anthropic":
            return self.anthropic_api_key
        if self.llm_provider == "openai":
            return self.openai_api_key
        return ""

    @property
    def api_base_url(self) -> str:
        return self.llm_base_url.rstrip("/") or "https://api.openai.com/v1"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def db_file(self) -> Path:
        p = Path(self.db_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def cli_workdir(self) -> str:
        """Neutral directory to run Claude Code in.

        Running inside the repo would leak the project's CLAUDE.md and file
        context into the call; a temp directory keeps results independent of the
        working directory.
        """
        path = Path(tempfile.gettempdir()) / "jobagent-cli"
        path.mkdir(parents=True, exist_ok=True)
        return str(path)

    @property
    def adzuna_enabled(self) -> bool:
        return bool(self.adzuna_app_id and self.adzuna_app_key)

    @property
    def jooble_enabled(self) -> bool:
        return bool(self.jooble_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
