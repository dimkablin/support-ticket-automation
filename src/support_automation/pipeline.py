from __future__ import annotations

import hashlib
import time
from dataclasses import replace
from typing import Any

from .adapters import normalize_ticket
from .classifier import ThemeClassifier
from .knowledge import KnowledgeBase
from .models import Action, Classification, Decision
from .persistence import PostgresAudit, RedisCache
from .policy import decide_action
from .privacy import mask_pii
from .providers import LLMProvider
from .tracing import TicketTrace

FALLBACK_RESPONSE = "Автоматическая обработка временно недоступна. Тикет передан оператору."
HUMAN_NEED_RESPONSE = "Тикет передан оператору без генерации ответа."


class TicketPipeline:
    kb_version = "kb-v3-rubert-tiny2-actions"

    def __init__(
        self,
        classifier: ThemeClassifier,
        knowledge: KnowledgeBase,
        provider: LLMProvider,
        confidence_threshold: float = 0.22,
        cache: RedisCache | None = None,
        audit: PostgresAudit | None = None,
        langfuse: tuple[str, str, str] = ("", "", ""),
    ) -> None:
        self.classifier = classifier
        self.knowledge = knowledge
        self.provider = provider
        self.confidence_threshold = confidence_threshold
        self.cache = cache
        self.audit = audit
        self.langfuse = langfuse

    def process(
        self, channel: str, payload: dict[str, Any], ticket_id: str | None = None
    ) -> Decision:
        started = time.perf_counter()
        ticket = normalize_ticket(channel, payload, ticket_id)
        masked_query = mask_pii(ticket.query)
        cache_key = self._cache_key(masked_query)

        with TicketTrace(
            "process-ticket",
            {"ticket_id": ticket.id, "query": masked_query, "channel": channel},
            *self.langfuse,
        ) as trace:
            cached = self._cache_get(cache_key)
            if cached:
                decision = self._from_cache(
                    cached, ticket.id, channel, ticket.device, started, trace.trace_id
                )
                if not self._audit(decision) and decision.action is not Action.HUMAN_NEED:
                    decision = replace(
                        decision, action=Action.HUMAN_NEED, fallback_reason="AuditUnavailable"
                    )
                trace.finish(self._trace_output(decision))
                return decision

            classification = self.classifier.predict(masked_query)
            high_risk, action = decide_action(classification, self.confidence_threshold)
            document_id: str | None = None
            fallback_reason: str | None = None
            response = HUMAN_NEED_RESPONSE
            if action is not Action.HUMAN_NEED:
                try:
                    documents = self.knowledge.search(masked_query, top_k=3)
                    if not documents:
                        raise LookupError("База знаний не вернула документы")
                    document_id = documents[0].document_id
                    response = self.provider.generate(masked_query, documents[0].content)
                except Exception as error:  # noqa: BLE001 - внешние AI/RAG провайдеры обязаны деградировать
                    action = Action.HUMAN_NEED
                    response = FALLBACK_RESPONSE
                    fallback_reason = type(error).__name__

            decision = Decision(
                ticket_id=ticket.id,
                masked_query=masked_query,
                channel=channel,
                device=ticket.device,
                classification=classification,
                high_risk=high_risk,
                action=action,
                response=response,
                document_id=document_id,
                cache_hit=False,
                latency_ms=(time.perf_counter() - started) * 1000,
                trace_id=trace.trace_id,
                fallback_reason=fallback_reason,
            )
            audit_ok = self._audit(decision)
            if not audit_ok and decision.action is not Action.HUMAN_NEED:
                decision = replace(
                    decision,
                    action=Action.HUMAN_NEED,
                    fallback_reason="AuditUnavailable",
                )
            elif audit_ok:
                self._cache_set(cache_key, decision)
            trace.finish(self._trace_output(decision))
            return decision

    def _cache_key(self, query: str) -> str:
        value = f"{query}|{self.classifier.version}|{self.kb_version}|{self.provider.name}"
        return "ticket:" + hashlib.sha256(value.encode()).hexdigest()

    def _cache_get(self, key: str) -> dict[str, Any] | None:
        if not self.cache:
            return None
        try:
            return self.cache.get(key)
        except Exception:  # noqa: BLE001 - кэш не должен останавливать обработку
            return None

    def _cache_set(self, key: str, decision: Decision) -> None:
        if not self.cache or decision.fallback_reason:
            return
        try:
            self.cache.set(key, decision.to_dict())
        except Exception:  # noqa: BLE001,S110 - best-effort кэш
            pass

    def _audit(self, decision: Decision) -> bool:
        if not self.audit:
            return True
        try:
            self.audit.write(decision, self.classifier.version, self.kb_version)
            return True
        except Exception:  # noqa: BLE001 - сбой аудита меняет auto_reply на human_need
            return False

    @staticmethod
    def _from_cache(
        value: dict[str, Any],
        ticket_id: str,
        channel: str,
        device: str,
        started: float,
        trace_id: str | None,
    ) -> Decision:
        raw_classification = value["classification"]
        classification = Classification(
            theme=raw_classification["theme"],
            confidence=float(raw_classification["confidence"]),
            top3=tuple((item[0], float(item[1])) for item in raw_classification["top3"]),
        )
        return Decision(
            ticket_id=ticket_id,
            masked_query=value["masked_query"],
            channel=channel,
            device=device,
            classification=classification,
            high_risk=bool(value["high_risk"]),
            action=Action(value["action"]),
            response=value["response"],
            document_id=value.get("document_id"),
            cache_hit=True,
            latency_ms=(time.perf_counter() - started) * 1000,
            trace_id=trace_id,
        )

    @staticmethod
    def _trace_output(decision: Decision) -> dict[str, Any]:
        return {
            "theme": decision.classification.theme,
            "confidence": decision.classification.confidence,
            "high_risk": decision.high_risk,
            "action": decision.action.value,
            "cache_hit": decision.cache_hit,
            "fallback_reason": decision.fallback_reason,
        }
