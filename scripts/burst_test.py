from __future__ import annotations

import argparse
import json
import time

from support_automation.classifier import load_rows
from support_automation.environment import Settings
from support_automation.queueing import (
    DLQ,
    GENERATE_QUEUE,
    HUMAN_QUEUE,
    INCOMING_QUEUE,
    RabbitPublisher,
    TicketEnvelope,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Burst-тест RabbitMQ без LLM-as-a-judge")
    parser.add_argument("--count", type=int, default=20_000)
    parser.add_argument(
        "--rate",
        type=float,
        default=0,
        help="Сообщений/с; 0 публикует максимально быстро",
    )
    parser.add_argument("--provider", choices=["fake", "litellm"], default="fake")
    args = parser.parse_args()
    if args.count < 1 or args.rate < 0:
        parser.error("count должен быть > 0, rate — >= 0")

    settings = Settings.from_env()
    rows = load_rows(settings.root / "data" / "query_dataset.jsonl")
    started = time.perf_counter()
    failures = 0
    depths: dict[str, int] = {}
    with RabbitPublisher(settings.rabbitmq_url, settings.rabbitmq_max_length) as publisher:
        for index in range(args.count):
            row = rows[index % len(rows)]
            envelope = TicketEnvelope.from_payload(
                str(row["channel"]),
                dict(row["payload"]),
                args.provider,
                ticket_id=f"burst-{time.time_ns()}-{index}",
            )
            try:
                publisher.publish(envelope)
            except Exception:  # noqa: BLE001 - test продолжает считать reject-publish
                failures += 1
            if args.rate:
                target_elapsed = (index + 1) / args.rate
                time.sleep(max(target_elapsed - (time.perf_counter() - started), 0))

        if not publisher.channel:
            raise RuntimeError("RabbitMQ channel закрыт до получения queue depth")
        for queue in (INCOMING_QUEUE, GENERATE_QUEUE, HUMAN_QUEUE, DLQ):
            state = publisher.channel.queue_declare(queue=queue, passive=True)
            depths[queue] = state.method.message_count

    elapsed = time.perf_counter() - started
    result = {
        "requested": args.count,
        "confirmed": args.count - failures,
        "rejected": failures,
        "elapsed_seconds": round(elapsed, 3),
        "publish_rate_per_second": round((args.count - failures) / elapsed, 1),
        "queue_depth": depths,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()
