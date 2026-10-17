"""Application configuration, loaded from environment / .env file."""

from __future__ import annotations

import secrets
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="WAVELANE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- identity -----------------------------------------------------------
    app_name: str = "Wavelane"
    environment: str = "development"
    debug: bool = True

    # --- security -----------------------------------------------------------
    secret_key: str = Field(default_factory=lambda: secrets.token_urlsafe(48))
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 30
    refresh_token_ttl_days: int = 60
    allow_registration: bool = True

    # --- storage ------------------------------------------------------------
    database_url: str = "sqlite+aiosqlite:///./wavelane.db"
    storage_root: Path = Path("./storage")
    max_upload_bytes: int = 512 * 1024 * 1024  # 512 MiB

    # --- streaming ----------------------------------------------------------
    stream_chunk_bytes: int = 256 * 1024
    stream_token_ttl_seconds: int = 60 * 60 * 6

    # --- audio analysis -----------------------------------------------------
    ffmpeg_path: str = ""
    ffprobe_path: str = ""
    analyze_on_upload: bool = True

    # --- api ----------------------------------------------------------------
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])
    api_prefix: str = "/api/v1"

    @field_validator("storage_root")
    @classmethod
    def _resolve_storage(cls, value: Path) -> Path:
        return value.expanduser().resolve()

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def audio_dir(self) -> Path:
        return self.storage_root / "audio"

    @property
    def cover_dir(self) -> Path:
        return self.storage_root / "covers"

    @property
    def avatar_dir(self) -> Path:
        return self.storage_root / "avatars"

    @property
    def incoming_dir(self) -> Path:
        return self.storage_root / "incoming"

    def ensure_directories(self) -> None:
        for directory in (self.audio_dir, self.cover_dir, self.avatar_dir, self.incoming_dir):
            directory.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
