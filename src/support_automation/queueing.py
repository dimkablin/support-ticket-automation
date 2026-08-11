from __future__ import annotations

import json
import time
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any, Self

import pika

from .adapters import normalize_ticket
from .models import Action, Channel
from .privacy import mask_pii

INCOMING_QUEUE = "tickets.incoming"
GENERATE_QUEUE = "tickets.generate"
HUMAN_QUEUE = "tickets.human"
DLQ = "tickets.dlq"
DEAD_LETTER_EXCHANGE = "tickets.dlx"
PROVIDERS = frozenset({"fake", "litellm"})


@dataclass(frozen=True)
class TicketEnvelope:
    ticket_id: str
    channel: str
    device: str
    query: str
    provider: str
    enqueued_at: float

    def __post_init__(self) -> None:
        Channel(self.channel)
        if self.provider not in PROVIDERS:
            raise ValueError(f"Неизвестный LLM provider: {self.provider}")
        if not self.ticket_id or not self.device or not self.query:
            raise ValueError("Queue message содержит пустое обязательное поле")

    @classmethod
    def from_payload(
        cls,
        channel: str,
        payload: dict[str, Any],
        provider: str = "fake",
        ticket_id: str | None = None,
    ) -> TicketEnvelope:
        ticket = normalize_ticket(channel, payload, ticket_id)
        return cls(
            ticket_id=ticket.id,
            channel=ticket.channel.value,
            device=ticket.device,
            query=mask_pii(ticket.query),
            provider=provider,
            enqueued_at=time.time(),
        )

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, separators=(",", ":"))

    @classmethod
    def from_json(cls, raw: bytes | str) -> TicketEnvelope:
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise TypeError("Queue message должен быть JSON object")
        return cls(
            ticket_id=str(value["ticket_id"]),
            channel=str(value["channel"]),
            device=str(value["device"]),
            query=str(value["query"]),
            provider=str(value["provider"]),
            enqueued_at=float(value["enqueued_at"]),
        )


def route_queue(action: Action) -> str:
    return HUMAN_QUEUE if action is Action.HUMAN_NEED else GENERATE_QUEUE


def delivery_attempt(headers: Mapping[str, Any] | None) -> int:
    return int((headers or {}).get("x-delivery-count", 0)) + 1


def queue_arguments(max_length: int) -> dict[str, str | int]:
    return {
        "x-queue-type": "quorum",
        "x-max-length": max_length,
        "x-overflow": "reject-publish",
        "x-delivery-limit": 3,
        "x-dead-letter-strategy": "at-least-once",
        "x-dead-letter-exchange": DEAD_LETTER_EXCHANGE,
        "x-dead-letter-routing-key": DLQ,
    }


def terminal_queue_arguments(max_length: int) -> dict[str, str | int]:
    return {
        "x-queue-type": "quorum",
        "x-max-length": max_length,
        "x-overflow": "reject-publish",
    }


def declare_topology(
    channel: pika.adapters.blocking_connection.BlockingChannel, max_length: int
) -> None:
    channel.exchange_declare(
        exchange=DEAD_LETTER_EXCHANGE,
        exchange_type="direct",
        durable=True,
    )
    terminal = terminal_queue_arguments(max_length)
    channel.queue_declare(queue=DLQ, durable=True, arguments=terminal)
    channel.queue_bind(queue=DLQ, exchange=DEAD_LETTER_EXCHANGE, routing_key=DLQ)
    channel.queue_declare(queue=HUMAN_QUEUE, durable=True, arguments=terminal)
    work = queue_arguments(max_length)
    channel.queue_declare(queue=INCOMING_QUEUE, durable=True, arguments=work)
    channel.queue_declare(queue=GENERATE_QUEUE, durable=True, arguments=work)


def publish_confirmed(
    channel: pika.adapters.blocking_connection.BlockingChannel,
    queue: str,
    body: str,
    message_id: str,
) -> None:
    confirmed = channel.basic_publish(
        exchange="",
        routing_key=queue,
        body=body.encode("utf-8"),
        properties=pika.BasicProperties(
            content_type="application/json",
            delivery_mode=pika.DeliveryMode.Persistent,
            message_id=message_id,
            timestamp=int(time.time()),
        ),
        mandatory=True,
    )
    if confirmed is False:
        raise RuntimeError(f"RabbitMQ не подтвердил публикацию в {queue}")


class RabbitPublisher:
    def __init__(self, url: str, max_length: int = 50_000) -> None:
        self.url = url
        self.max_length = max_length
        self.connection: pika.BlockingConnection | None = None
        self.channel: pika.adapters.blocking_connection.BlockingChannel | None = None

    def __enter__(self) -> Self:
        parameters = pika.URLParameters(self.url)
        parameters.blocked_connection_timeout = 10
        self.connection = pika.BlockingConnection(parameters)
        self.channel = self.connection.channel()
        self.channel.confirm_delivery()
        declare_topology(self.channel, self.max_length)
        return self

    def publish(self, envelope: TicketEnvelope) -> None:
        if not self.channel:
            raise RuntimeError("RabbitPublisher должен использоваться как context manager")
        publish_confirmed(
            self.channel,
            INCOMING_QUEUE,
            envelope.to_json(),
            envelope.ticket_id,
        )

    def publish_ticket(
        self,
        channel: str,
        payload: dict[str, Any],
        provider: str = "fake",
        ticket_id: str | None = None,
    ) -> str:
        envelope = TicketEnvelope.from_payload(channel, payload, provider, ticket_id)
        self.publish(envelope)
        return envelope.ticket_id

    def __exit__(self, *_: object) -> None:
        if self.connection and self.connection.is_open:
            self.connection.close()
