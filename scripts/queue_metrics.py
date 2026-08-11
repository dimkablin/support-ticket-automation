from __future__ import annotations

import json
import os
import time
from collections import defaultdict

import httpx
from dotenv import load_dotenv
from prometheus_client.parser import text_string_to_metric_families

from support_automation.environment import ROOT


def samples(url: str) -> list[object]:
    response = httpx.get(url, timeout=10)
    response.raise_for_status()
    return [
        sample
        for family in text_string_to_metric_families(response.text)
        for sample in family.samples
    ]


def main() -> None:
    load_dotenv(ROOT / ".env", override=False)
    rabbit_url = os.getenv("RABBITMQ_METRICS_URL", "http://localhost:15693")
    worker_url = os.getenv("WORKER_METRICS_URL", "http://localhost:9100")
    rabbit = samples(
        f"{rabbit_url}/metrics/detailed?family=queue_coarse_metrics&family=queue_metrics"
    )
    worker_error: str | None = None
    try:
        worker = samples(f"{worker_url}/metrics")
    except httpx.HTTPError as error:
        worker = []
        worker_error = type(error).__name__

    queues: dict[str, dict[str, float]] = defaultdict(dict)
    now = time.time()
    for sample in rabbit:
        queue = sample.labels.get("queue")
        if not queue:
            continue
        if sample.name.endswith("queue_messages"):
            queues[queue]["depth"] = sample.value
        elif sample.name.endswith("queue_head_message_timestamp"):
            queues[queue]["oldest_age_seconds"] = max(now - sample.value, 0)

    worker_metrics: dict[str, float] = {}
    for sample in worker:
        if sample.name == "ticket_worker_llm_calls_total":
            worker_metrics["llm_calls"] = sample.value
        elif sample.name == "ticket_worker_throughput_per_second":
            worker_metrics["throughput_per_second"] = sample.value
        elif sample.name == "ticket_worker_failures_total":
            worker_metrics["failures"] = worker_metrics.get("failures", 0) + sample.value
        elif sample.name == "ticket_worker_oldest_message_age_seconds":
            queue = sample.labels["queue"]
            queues[queue]["oldest_age_seconds"] = sample.value

    print(
        json.dumps(
            {"queues": queues, "worker": worker_metrics, "worker_error": worker_error},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
