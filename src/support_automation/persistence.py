from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import psycopg
import redis

from .models import Decision


class RedisCache:
    def __init__(self, url: str, ttl_seconds: int = 900) -> None:
        self.client = redis.Redis.from_url(url, decode_responses=True, socket_timeout=1)
        self.ttl_seconds = ttl_seconds

    def get(self, key: str) -> dict[str, Any] | None:
        value = self.client.get(key)
        return json.loads(value) if value else None

    def set(self, key: str, value: Mapping[str, Any]) -> None:
        self.client.setex(key, self.ttl_seconds, json.dumps(value, ensure_ascii=False))


class PostgresAudit:
    def __init__(self, url: str) -> None:
        self.url = url

    def initialize(self) -> None:
        with psycopg.connect(self.url) as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS ticket_decisions (
                    id BIGSERIAL PRIMARY KEY,
                    ticket_id TEXT NOT NULL,
                    masked_query TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    device TEXT NOT NULL,
                    predicted_theme TEXT NOT NULL,
                    confidence DOUBLE PRECISION NOT NULL,
                    top3 JSONB NOT NULL,
                    high_risk BOOLEAN NOT NULL,
                    action TEXT NOT NULL,
                    document_id TEXT,
                    cache_hit BOOLEAN NOT NULL,
                    classifier_version TEXT NOT NULL,
                    kb_version TEXT NOT NULL,
                    langfuse_trace_id TEXT,
                    fallback_reason TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )

    def write(self, decision: Decision, classifier_version: str, kb_version: str) -> None:
        with psycopg.connect(self.url) as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO ticket_decisions (
                    ticket_id, masked_query, channel, device, predicted_theme, confidence,
                    top3, high_risk, action, document_id, cache_hit, classifier_version,
                    kb_version, langfuse_trace_id, fallback_reason
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    decision.ticket_id,
                    decision.masked_query,
                    decision.channel,
                    decision.device,
                    decision.classification.theme,
                    decision.classification.confidence,
                    json.dumps(decision.classification.top3),
                    decision.high_risk,
                    decision.action.value,
                    decision.document_id,
                    decision.cache_hit,
                    classifier_version,
                    kb_version,
                    decision.trace_id,
                    decision.fallback_reason,
                ),
            )
