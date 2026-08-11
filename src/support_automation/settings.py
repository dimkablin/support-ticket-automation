from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    root: Path
    classifier_path: Path
    lightrag_url: str
    lightrag_api_key: str
    redis_url: str
    postgres_url: str
    langfuse_public_key: str
    langfuse_secret_key: str
    langfuse_base_url: str
    litellm_model: str
    litellm_api_base: str
    litellm_api_key: str
    confidence_threshold: float

    @classmethod
    def from_env(cls) -> Settings:
        root = Path(__file__).resolve().parents[2]
        return cls(
            root=root,
            classifier_path=Path(
                os.getenv("CLASSIFIER_PATH", root / "models/theme_classifier.joblib")
            ),
            lightrag_url=os.getenv("LIGHTRAG_BASE_URL", "http://localhost:9621"),
            lightrag_api_key=os.getenv("LIGHTRAG_API_KEY", ""),
            redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
            postgres_url=os.getenv(
                "POSTGRES_URL",
                "postgresql://support:support@localhost:5434/support?connect_timeout=3",
            ),
            langfuse_public_key=os.getenv("LANGFUSE_PUBLIC_KEY", ""),
            langfuse_secret_key=os.getenv("LANGFUSE_SECRET_KEY", ""),
            langfuse_base_url=os.getenv("LANGFUSE_BASE_URL", "http://localhost:3000"),
            litellm_model=os.getenv("LITELLM_MODEL", "openai/qwen3:8b"),
            litellm_api_base=os.getenv("LITELLM_API_BASE", "http://localhost:11434/v1"),
            litellm_api_key=os.getenv("LITELLM_API_KEY", "ollama"),
            confidence_threshold=float(os.getenv("CLASSIFIER_CONFIDENCE_THRESHOLD", "0.22")),
        )
