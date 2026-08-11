from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable
from typing import Any

import pika
from prometheus_client import Counter, Gauge, Histogram, start_http_server

from .adapters import TEXT_FIELDS
from .bootstrap import build_pipeline
from .environment import Settings
from .models import Action, Channel, Decision
from .policy import decide_action
from .providers import LLMProvider
from .queueing import (
    GENERATE_QUEUE,
    HUMAN_QUEUE,
    INCOMING_QUEUE,
    TicketEnvelope,
    declare_topology,
    delivery_attempt,
    publish_confirmed,
    route_queue,
)

LOG = logging.getLogger("support-worker")
PROCESSED = Counter(
    "ticket_worker_processed_total",
    "Обработанные queue stages",
    ("queue", "action"),
)
FAILURES = Counter(
    "ticket_worker_failures_total",
    "Неуспешные попытки обработки до retry/DLQ",
    ("queue",),
)
LLM_CALLS = Counter("ticket_worker_llm_calls_total", "Фактические вызовы LLM provider")
QUEUE_WAIT = Histogram(
    "ticket_worker_queue_wait_seconds",
    "Возраст сообщения на момент обработки",
    ("queue",),
    buckets=(0.1, 0.5, 1, 5, 15, 60, 300, 900, 3600),
)
OLDEST_MESSAGE_AGE = Gauge(
    "ticket_worker_oldest_message_age_seconds",
    "Возраст head-сообщения при последней доставке",
    ("queue",),
)
THROUGHPUT = Gauge(
    "ticket_worker_throughput_per_second",
    "Средний throughput worker с момента запуска",
)
_started = time.monotonic()
_processed = 0
_metrics_lock = threading.Lock()


class MetricsProvider:
    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider
        self.name = provider.name

    def generate(self, query: str, context: str) -> str:
        LLM_CALLS.inc()
        return self.provider.generate(query, context)


def _record_processed(queue: str, action: Action) -> None:
    global _processed
    PROCESSED.labels(queue, action.value).inc()
    with _metrics_lock:
        _processed += 1
        THROUGHPUT.set(_processed / max(time.monotonic() - _started, 0.001))


def _payload(envelope: TicketEnvelope) -> dict[str, str]:
    channel = Channel(envelope.channel)
    return {"device": envelope.device, TEXT_FIELDS[channel]: envelope.query}


def _decision_json(decision: Decision) -> str:
    return json.dumps(decision.to_dict(), ensure_ascii=False, separators=(",", ":"))


def _pipeline_factory(settings: Settings) -> Callable[[str], Any]:
    pipelines: dict[str, Any] = {}

    def get(provider_name: str) -> Any:
        if provider_name not in pipelines:
            pipeline = build_pipeline(settings, provider_name)
            pipeline.provider = MetricsProvider(pipeline.provider)
            pipelines[provider_name] = pipeline
        return pipelines[provider_name]

    return get


def _process_incoming(
    channel: pika.adapters.blocking_connection.BlockingChannel,
    envelope: TicketEnvelope,
    pipeline: Any,
) -> Action:
    classification = pipeline.classifier.predict(envelope.query)
    _, action = decide_action(classification, pipeline.confidence_threshold)
    destination = route_queue(action)
    if destination == GENERATE_QUEUE:
        publish_confirmed(channel, destination, envelope.to_json(), envelope.ticket_id)
        return action

    decision = pipeline.process(
        envelope.channel,
        _payload(envelope),
        envelope.ticket_id,
    )
    publish_confirmed(channel, HUMAN_QUEUE, _decision_json(decision), envelope.ticket_id)
    return decision.action


def _process_generate(
    channel: pika.adapters.blocking_connection.BlockingChannel,
    envelope: TicketEnvelope,
    pipeline: Any,
) -> Action:
    decision = pipeline.process(
        envelope.channel,
        _payload(envelope),
        envelope.ticket_id,
    )
    if decision.action is not Action.AUTO_REPLY:
        publish_confirmed(channel, HUMAN_QUEUE, _decision_json(decision), envelope.ticket_id)
    return decision.action


def _consume_once(settings: Settings, consumer_number: int) -> None:
    parameters = pika.URLParameters(settings.rabbitmq_url)
    parameters.blocked_connection_timeout = 10
    connection = pika.BlockingConnection(parameters)
    channel = connection.channel()
    channel.confirm_delivery()
    declare_topology(channel, settings.rabbitmq_max_length)
    channel.basic_qos(prefetch_count=settings.rabbitmq_prefetch)
    get_pipeline = _pipeline_factory(settings)

    def callback(queue: str) -> Callable[..., None]:
        def handle(
            broker_channel: pika.adapters.blocking_connection.BlockingChannel,
            method: Any,
            properties: pika.BasicProperties,
            body: bytes,
        ) -> None:
            try:
                envelope = TicketEnvelope.from_json(body)
                message_age = max(time.time() - envelope.enqueued_at, 0)
                QUEUE_WAIT.labels(queue).observe(message_age)
                OLDEST_MESSAGE_AGE.labels(queue).set(message_age)
                pipeline = get_pipeline(envelope.provider)
                action = (
                    _process_incoming(broker_channel, envelope, pipeline)
                    if queue == INCOMING_QUEUE
                    else _process_generate(broker_channel, envelope, pipeline)
                )
                broker_channel.basic_ack(method.delivery_tag)
                _record_processed(queue, action)
            except Exception:
                FAILURES.labels(queue).inc()
                attempt = delivery_attempt(properties.headers)
                LOG.exception(
                    "Consumer %s failed message from %s attempt=%s",
                    consumer_number,
                    queue,
                    attempt,
                )
                broker_channel.basic_reject(method.delivery_tag, requeue=attempt < 3)

        return handle

    channel.basic_consume(INCOMING_QUEUE, callback(INCOMING_QUEUE), auto_ack=False)
    channel.basic_consume(GENERATE_QUEUE, callback(GENERATE_QUEUE), auto_ack=False)
    LOG.info("Consumer %s started", consumer_number)
    channel.start_consuming()


def _consume_forever(settings: Settings, consumer_number: int) -> None:
    while True:
        try:
            _consume_once(settings, consumer_number)
        except Exception:
            LOG.exception("Consumer %s disconnected; retry in 3 seconds", consumer_number)
            time.sleep(3)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    settings = Settings.from_env()
    start_http_server(settings.worker_metrics_port)
    for number in range(settings.llm_concurrency):
        threading.Thread(
            target=_consume_forever,
            args=(settings, number + 1),
            daemon=True,
            name=f"ticket-consumer-{number + 1}",
        ).start()
    LOG.info(
        "Worker started: concurrency=%s prefetch=%s metrics_port=%s",
        settings.llm_concurrency,
        settings.rabbitmq_prefetch,
        settings.worker_metrics_port,
    )
    threading.Event().wait()


if __name__ == "__main__":
    main()
