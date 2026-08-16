import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

LLMProvider = Literal["claude_cli", "anthropic", "openai"]

#: Sağlayıcı başına varsayılan model.
#:
#: "openai" bilerek boş: OpenAI-uyumlu uçlarda (OpenRouter, Groq, Ollama,
#: LM Studio, vLLM…) geçerli model adı sunucuya göre değişiyor. Tahmin etmek
#: kullanıcıyı "model not found" hatasına götürmekten başka işe yaramaz;
#: bunun yerine LLM_MODEL'i zorunlu tutup net hata veriyoruz.
DEFAULT_MODELS: dict[str, str] = {
    "claude_cli": "claude-opus-5",
    "anthropic": "claude-opus-5",
    "openai": "",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # -- Model erişimi ------------------------------------------------------
    # Üç sağlayıcı: bkz. app/llm.py
    #   claude_cli  Claude Code CLI (`claude -p`) — API anahtarı yok, üyelik oturumu
    #   anthropic   Anthropic API — ANTHROPIC_API_KEY
    #   openai      OpenAI ve OpenAI-uyumlu her uç (LLM_BASE_URL ile)
    llm_provider: LLMProvider = "claude_cli"
    llm_model: str = ""          # boş → DEFAULT_MODELS
    llm_api_key: str = ""        # boş → ANTHROPIC_API_KEY / OPENAI_API_KEY
    llm_base_url: str = ""       # yalnızca openai sağlayıcısı; boş → api.openai.com
    llm_timeout: float = 300.0
    llm_max_tokens: int = 16000
    # OpenAI-uyumlu sunucuların hepsi json_schema desteklemiyor (yerel modeller
    # çoğunlukla desteklemez). "auto" en güçlüsünden başlayıp hata alınca
    # sırayla düşer ve çalışan kipi hatırlar.
    llm_json_mode: Literal["auto", "schema", "object", "prompt"] = "auto"

    # Standart isimler — kullanıcı zaten ortamında taşıyor olabilir
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    # Yalnızca claude_cli sağlayıcısı için
    claude_cli: str = "claude"

    # Geriye dönük uyum: eski .env dosyalarındaki isimler
    agent_model: str = ""
    claude_timeout: float | None = None

    # -- Opsiyonel ilan kaynakları -----------------------------------------
    adzuna_app_id: str | None = None
    adzuna_app_key: str | None = None
    jooble_api_key: str | None = None
    # Jooble anahtarları BÖLGESELDİR: jooble.org anahtarı ABD indeksini
    # sorgular. Türkiye ilanları için anahtarı tr.jooble.org'dan alıp
    # bu değeri https://tr.jooble.org yap.
    jooble_host: str = "https://jooble.org"

    # -- Uygulama ----------------------------------------------------------
    db_path: str = "./data/jobsearch.db"
    cors_origins: str = "http://localhost:3001,http://localhost:3000"

    # Sağlayıcıya göre maliyet modeli değişiyor: Claude Code üyeliğinde token
    # başına ücret yok (duvar saatini optimize et — küçük parti, yüksek
    # paralellik), API sağlayıcılarında her çağrı ücretli. Varsayılanlar tek
    # dalgada bitecek şekilde seçildi (32 / 8 = 4 parti, 4 eşzamanlı); ücretli
    # bir sağlayıcı kullanıyorsan LLM_SCORE_LIMIT'i düşürmek doğrudan tasarruf.
    llm_score_limit: int = 32
    score_batch_size: int = 8
    max_concurrency: int = 4

    fetch_limit_per_source: int = 120
    http_timeout: float = 25.0

    # -- Türetilmiş değerler ------------------------------------------------
    @property
    def active_model(self) -> str:
        """Çağrılarda kullanılacak model adı (eski AGENT_MODEL da okunur)."""
        return self.llm_model or self.agent_model or DEFAULT_MODELS[self.llm_provider]

    @property
    def request_timeout(self) -> float:
        return self.claude_timeout if self.claude_timeout is not None else self.llm_timeout

    @property
    def api_key(self) -> str:
        """Seçili sağlayıcının anahtarı; claude_cli için anlamsız (boş döner)."""
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
        """Claude Code'un çalıştırılacağı nötr dizin.

        Depo içinde çalıştırmak projenin CLAUDE.md'sini ve dosya bağlamını
        çağrıya sızdırırdı; sonuçların çalışma dizininden bağımsız olması için
        geçici bir dizin kullanıyoruz.
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
