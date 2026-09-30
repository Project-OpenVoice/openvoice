"""
app/core/config.py

Pydantic-settings configuration loaded from environment variables / .env file.
All other modules import `get_settings()` — never instantiate Settings directly.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Decision Engine ---
    # "laya" | "multilingual" | "typed-decisions"
    model_decision: str = "laya"

    # --- Hardware Device ---
    # "auto" | "cuda" | "cpu"
    device: str = "auto"

    # --- Memory paths ---
    vault_path: Path = Path("./data/vault")
    sqlite_path: Path = Path("./data/sqlite/openvoice.db")
    chroma_path: Path = Path("./data/chroma")

    # --- Embeddings (sentence-transformers, fully local) ---
    embedding_model: str = "all-MiniLM-L6-v2"

    # --- Phase 1 only — unused in PRE-PHASE-0 ---
    ollama_host: str = "http://localhost:11434"
    model_chat: str = "qwen3:8b"

    # --- Cloud (always disabled in PRE-PHASE-0) ---
    cloud_enabled: bool = False


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the singleton settings instance."""
    return Settings()
