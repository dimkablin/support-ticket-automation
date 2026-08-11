from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    root: Path
    classifier_path: Path
    qdrant_url: str
    qdrant_collection: str
    qdrant_api_key: str
    embedding_url: str
    embedding_model: str
    embedding_dim: int
    redis_url: str
    postgres_url: str
    langfuse_public_key: str
    langfuse_secret_key: str
    langfuse_base_url: str
    litellm_model: str
    litellm_api_base: str
    litellm_api_key: str
    confidence_threshold: float
    rabbitmq_url: str
    rabbitmq_max_length: int
    rabbitmq_prefetch: int
    llm_concurrency: int
    worker_metrics_port: int

    @classmethod
    def from_env(cls, env_file: Path | None = None) -> Settings:
        load_dotenv(env_file or ROOT / ".env", override=False)
        return cls(
            root=ROOT,
            classifier_path=Path(
                os.getenv("CLASSIFIER_PATH", ROOT / "models/theme_classifier.joblib")
            ),
            qdrant_url=os.getenv("QDRANT_URL", "http://localhost:6333"),
            qdrant_collection=os.getenv("QDRANT_COLLECTION", "support_kb_rubert_tiny2"),
            qdrant_api_key=os.getenv("QDRANT_API_KEY", ""),
            embedding_url=os.getenv("EMBEDDING_BASE_URL", "http://localhost:8081/v1"),
            embedding_model=os.getenv("EMBEDDING_MODEL", "cointegrated/rubert-tiny2"),
            embedding_dim=int(os.getenv("EMBEDDING_DIM", "312")),
            redis_url=os.getenv("REDIS_URL", "redis://localhost:6380/0"),
            postgres_url=os.getenv(
                "POSTGRES_URL",
                "postgresql://support:support@localhost:5434/support?connect_timeout=3",
            ),
            langfuse_public_key=os.getenv("LANGFUSE_PUBLIC_KEY", ""),
            langfuse_secret_key=os.getenv("LANGFUSE_SECRET_KEY", ""),
            langfuse_base_url=os.getenv("LANGFUSE_BASE_URL", "http://localhost:3000"),
            litellm_model=os.getenv("LITELLM_MODEL", "openai/support-llm"),
            litellm_api_base=os.getenv("LITELLM_URL", "http://host.docker.internal:4000/v1"),
            litellm_api_key=os.getenv("LITELLM_API_KEY", ""),
            confidence_threshold=float(os.getenv("CLASSIFIER_CONFIDENCE_THRESHOLD", "0.22")),
            rabbitmq_url=os.getenv("RABBITMQ_URL", "amqp://support:support@localhost:5673/%2F"),
            rabbitmq_max_length=int(os.getenv("RABBITMQ_MAX_LENGTH", "50000")),
            rabbitmq_prefetch=int(os.getenv("RABBITMQ_PREFETCH", "1")),
            llm_concurrency=int(os.getenv("LLM_CONCURRENCY", "2")),
            worker_metrics_port=int(os.getenv("WORKER_METRICS_PORT", "9100")),
        )
