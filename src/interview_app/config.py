"""Application settings, loaded from environment variables / .env (pydantic-settings).

Why pydantic-settings instead of os.getenv: typed values, defaults in one place,
and validation errors at startup instead of deep inside a request.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Models offered in the sidebar selector: the three models allowed by the course brief.
# The first entry is the default. The guard model (Haiku 4.5) is deliberately not here.
AVAILABLE_MODELS: tuple[str, ...] = (
    "anthropic/claude-sonnet-5.5",
    "openai/gpt-6-luna",
    "openai/gpt-6.1-sol",
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    openrouter_api_key: SecretStr = SecretStr("")
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    default_model: str = AVAILABLE_MODELS[0]
    guard_model: str = "anthropic/claude-haiku-4.5"

    llm_guard_enabled: bool = True
    guard_fail_closed: bool = False

    max_session_cost_usd: float = 2.0

    app_title: str = "Hoot - AI Interview Prep"
    user_name: str = ""
    user_email: str = ""
    app_url: str = "http://localhost:8501"
    data_dir: Path = Path("data")  # roles.yaml, Sprint 1 JSON files, the SQLite file
    # SQLAlchemy URL: SQLite file locally, postgresql+psycopg://... in production.
    database_url: str = "sqlite:///data/hoot.db"

    @property
    def has_api_key(self) -> bool:
        return bool(self.openrouter_api_key.get_secret_value().strip())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
