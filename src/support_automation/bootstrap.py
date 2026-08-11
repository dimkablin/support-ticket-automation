from __future__ import annotations

from .classifier import ThemeClassifier
from .environment import Settings
from .knowledge import BGEClient, QdrantKnowledgeBase
from .persistence import PostgresAudit, RedisCache
from .pipeline import TicketPipeline
from .providers import FakeLLM, LiteLLMProvider


def build_pipeline(settings: Settings, provider_name: str) -> TicketPipeline:
    provider = (
        FakeLLM()
        if provider_name == "fake"
        else LiteLLMProvider(
            settings.litellm_model,
            settings.litellm_api_base,
            settings.litellm_api_key,
        )
    )
    audit = PostgresAudit(settings.postgres_url)
    audit.initialize()
    return TicketPipeline(
        classifier=ThemeClassifier.load(settings.classifier_path),
        knowledge=QdrantKnowledgeBase(
            settings.qdrant_url,
            settings.qdrant_collection,
            settings.qdrant_api_key,
            BGEClient(settings.bge_m3_url, settings.bge_m3_model),
            settings.bge_m3_dim,
        ),
        provider=provider,
        confidence_threshold=settings.confidence_threshold,
        cache=RedisCache(settings.redis_url),
        audit=audit,
        langfuse=(
            settings.langfuse_public_key,
            settings.langfuse_secret_key,
            settings.langfuse_base_url,
        ),
    )
