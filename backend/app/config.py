from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List


def _load_env_file():
    """Load variables from .env file if present (root or backend dir)."""
    env_paths = [
        Path(".env"),
        Path("../.env"),
        Path(__file__).resolve().parent.parent / ".env",
        Path(__file__).resolve().parent.parent.parent / ".env",
    ]
    for p in env_paths:
        if p.is_file():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        if k and k not in os.environ:
                            os.environ[k] = v
                break
            except Exception:
                pass


@dataclass(frozen=True)
class Settings:
    llm_api_keys: List[str] = field(default_factory=list)
    database_url: str = "sqlite:////data/app.db"
    allowed_origins: List[str] = field(default_factory=lambda: ["*"])
    enable_failure_simulation: bool = False
    llm_model: str = "groq/llama-3.3-70b-versatile"

    @property
    def key_ids(self) -> List[str]:
        return [f"key_{i+1}" for i in range(len(self.llm_api_keys))]

    @property
    def db_path(self) -> str:
        url = self.database_url
        if url.startswith("sqlite:////"):
            return url[len("sqlite:///"):]
        if url.startswith("sqlite:///"):
            return url[len("sqlite:///"):]
        return url


def load_settings() -> Settings:
    _load_env_file()

    raw_keys = os.getenv("LLM_API_KEYS", "")
    keys = [k.strip() for k in raw_keys.split(",") if k.strip()] if raw_keys else []

    raw_origins = os.getenv("ALLOWED_ORIGINS", "*")
    origins = [o.strip() for o in raw_origins.split(",") if o.strip()] if raw_origins else ["*"]

    return Settings(
        llm_api_keys=keys,
        database_url=os.getenv("DATABASE_URL", "sqlite:////data/app.db"),
        allowed_origins=origins,
        enable_failure_simulation=os.getenv("ENABLE_FAILURE_SIMULATION", "false").lower() == "true",
        llm_model=os.getenv("LLM_MODEL", "groq/llama-3.3-70b-versatile"),
    )
