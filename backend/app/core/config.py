from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / "backend" / ".env", PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "InsightOps Agent"
    version: str = "0.1.0"
    environment: str = "development"
    log_level: str = "INFO"

    runtime_dir: Path = PROJECT_ROOT / "runtime"
    llm_provider: Literal["mock", "openai_compatible"] = "mock"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4.1-mini"
    llm_timeout_seconds: int = Field(default=45, ge=1, le=180)
    llm_max_retries: int = Field(default=1, ge=0, le=5)

    query_timeout_seconds: float = Field(default=2.0, ge=0.1, le=30)
    max_result_rows: int = Field(default=100, ge=1, le=1000)
    max_upload_bytes: int = Field(default=10 * 1024 * 1024, ge=1024)
    max_upload_rows: int = Field(default=100_000, ge=1)
    max_upload_columns: int = Field(default=100, ge=1)
    max_history_messages: int = Field(default=12, ge=1, le=50)
    cors_origins: str = "http://localhost:5175,http://127.0.0.1:5175"

    @computed_field
    @property
    def app_db_path(self) -> Path:
        return self.runtime_dir / "app.sqlite3"

    @computed_field
    @property
    def checkpoint_db_path(self) -> Path:
        return self.runtime_dir / "checkpoints.sqlite3"

    @computed_field
    @property
    def datasets_dir(self) -> Path:
        return self.runtime_dir / "datasets"

    @computed_field
    @property
    def uploads_dir(self) -> Path:
        return self.runtime_dir / "uploads"

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    def ensure_runtime_dirs(self) -> None:
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.datasets_dir.mkdir(parents=True, exist_ok=True)
        self.uploads_dir.mkdir(parents=True, exist_ok=True)


def get_settings() -> Settings:
    return Settings()
