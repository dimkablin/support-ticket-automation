from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any


class Channel(StrEnum):
    CHAT = "chat"
    EMAIL = "email"
    WEB = "web"
    MOBILE = "mobile"


class Action(StrEnum):
    AUTO_CLOSE = "auto_close"
    HUMAN_REVIEW = "human_review"


@dataclass(frozen=True)
class Ticket:
    id: str
    query: str
    channel: Channel
    device: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class Classification:
    theme: str
    confidence: float
    top3: tuple[tuple[str, float], ...]


@dataclass(frozen=True)
class RetrievedDocument:
    document_id: str
    content: str
    score: float = 0.0


@dataclass(frozen=True)
class Decision:
    ticket_id: str
    masked_query: str
    channel: str
    device: str
    classification: Classification
    high_risk: bool
    action: Action
    response: str
    document_id: str | None
    cache_hit: bool
    latency_ms: float
    trace_id: str | None = None
    fallback_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
