"""Central application configuration.

All runtime configuration is read from environment variables (optionally via a
local `.env` file — see `.env.example` at the repo root). Nothing here should
contain secrets; this module only defines *where* to look for them.

Cloud fields (GCP project, Firestore, Cloud Storage bucket) are defined now so
that swapping local implementations for cloud-backed ones later does not
require touching business logic — see docs/architecture.md.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="STRATA_",
        extra="ignore",
    )

    # --- General ---
    app_name: str = "Strata"
    environment: str = "development"  # development | production
    log_level: str = "INFO"
    log_json: bool = False  # emit structured JSON logs (recommended in prod/Cloud Run)

    # --- API ---
    api_v1_prefix: str = "/api/v1"
    cors_allow_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # --- Storage ---
    # "local" uses the filesystem (StorageService local implementation).
    # "gcs" is reserved for the future Google Cloud Storage implementation.
    storage_backend: str = "local"
    local_storage_dir: Path = Path("./data")

    # --- Persistence ---
    # "memory" uses the in-process RunRepository implementation.
    # "firestore" is reserved for the future Firestore-backed implementation.
    repository_backend: str = "memory"

    # --- Google Cloud (unused until cloud backends are wired in) ---
    gcp_project_id: str | None = None
    gcs_bucket_name: str | None = None
    firestore_database: str | None = None

    # --- PrusaSlicer ---
    prusaslicer_binary_path: str = "prusa-slicer"
    prusaslicer_timeout_seconds: int = 300

    # --- Agent planner: "deterministic" (default, offline, free) or
    # "gemini" (real Gemini + Google ADK call). Automated tests always use
    # deterministic mode unless explicitly testing the Gemini planner.
    planner_mode: str = "deterministic"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.5-flash"


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance.

    Cached because Settings parses the environment/`.env` on construction;
    every call site should share one instance for the process lifetime.
    """
    return Settings()
