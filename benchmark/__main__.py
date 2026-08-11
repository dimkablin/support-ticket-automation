from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path

from sklearn.metrics import accuracy_score, f1_score

from benchmark.metrics import fact_coverage, forbidden_fact_rate, reciprocal_rank, token_f1
from support_automation.classifier import ThemeClassifier, load_rows
from support_automation.environment import Settings
from support_automation.knowledge import LightRAGClient
from support_automation.policy import HIGH_RISK_THEMES, decide_action
from support_automation.providers import FakeLLM, LiteLLMProvider

ROOT = Path(__file__).resolve().parents[1]


def percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    return ordered[min(int((len(ordered) - 1) * quantile), len(ordered) - 1)]


def main() -> None:
    settings = Settings.from_env()
    parser = argparse.ArgumentParser(description="Быстрый benchmark без LLM-as-a-judge")
    parser.add_argument("--live", action="store_true", help="Проверить реальный LightRAG")
    parser.add_argument("--provider", choices=["fake", "litellm"], default="fake")
    args = parser.parse_args()

    rows = [
        row for row in load_rows(ROOT / "data" / "query_dataset.jsonl") if row["split"] == "test"
    ]
    classifier = ThemeClassifier.load(ROOT / "models" / "theme_classifier.joblib")
    predictions = []
    latencies = []
    for row in rows:
        started = time.perf_counter()
        predictions.append(classifier.predict(row["query"]))
        latencies.append((time.perf_counter() - started) * 1000)

    true_themes = [row["theme"] for row in rows]
    predicted_themes = [prediction.theme for prediction in predictions]
    true_risk = [bool(row["high_risk"]) for row in rows]
    predicted_risk = [prediction.theme in HIGH_RISK_THEMES for prediction in predictions]
    risk_positives = sum(true_risk)
    high_risk_recall = (
        sum(
            expected and predicted
            for expected, predicted in zip(true_risk, predicted_risk, strict=True)
        )
        / risk_positives
    )
    predicted_actions = [decide_action(prediction)[1].value for prediction in predictions]
    auto_close_indexes = [
        index for index, action in enumerate(predicted_actions) if action == "auto_close"
    ]
    auto_close_precision = (
        sum(rows[index]["expected_action"] == "auto_close" for index in auto_close_indexes)
        / len(auto_close_indexes)
        if auto_close_indexes
        else 1.0
    )

    results: dict[str, object] = {
        "mode": "live" if args.live else "classifier-only",
        "tickets": len(rows),
        "classifier_accuracy": accuracy_score(true_themes, predicted_themes),
        "classifier_macro_f1": f1_score(true_themes, predicted_themes, average="macro"),
        "classifier_top3_accuracy": sum(
            row["theme"] in {theme for theme, _ in prediction.top3}
            for row, prediction in zip(rows, predictions, strict=True)
        )
        / len(rows),
        "high_risk_recall": high_risk_recall,
        "high_risk_false_negatives": sum(
            expected and not predicted
            for expected, predicted in zip(true_risk, predicted_risk, strict=True)
        ),
        "action_accuracy": accuracy_score(
            [row["expected_action"] for row in rows], predicted_actions
        ),
        "auto_close_precision": auto_close_precision,
        "hot_path_p50_ms": statistics.median(latencies),
        "hot_path_p95_ms": percentile(latencies, 0.95),
    }

    if args.live:
        knowledge = LightRAGClient(
            settings.lightrag_url,
            settings.lightrag_api_key,
        )
        provider = (
            FakeLLM()
            if args.provider == "fake"
            else LiteLLMProvider(
                settings.litellm_model,
                settings.litellm_api_base,
                settings.litellm_api_key,
            )
        )
        ranks: list[float] = []
        hit1: list[bool] = []
        recall3: list[bool] = []
        coverage: list[float] = []
        forbidden: list[float] = []
        answer_f1: list[float] = []
        for row in rows:
            documents = knowledge.search(row["query"], top_k=3)
            ids = [document.document_id for document in documents]
            ranks.append(reciprocal_rank(row["expected_document_id"], ids))
            hit1.append(bool(ids) and ids[0] == row["expected_document_id"])
            recall3.append(row["expected_document_id"] in ids)
            answer = provider.generate(row["query"], documents[0].content) if documents else ""
            coverage.append(fact_coverage(answer, row["required_facts"]))
            forbidden.append(forbidden_fact_rate(answer, row["forbidden_facts"]))
            answer_f1.append(token_f1(answer, row["answer"]))
        results.update(
            {
                "retrieval_hit_at_1": sum(hit1) / len(hit1),
                "retrieval_recall_at_3": sum(recall3) / len(recall3),
                "retrieval_mrr": statistics.mean(ranks),
                "required_fact_coverage": statistics.mean(coverage),
                "forbidden_fact_rate": statistics.mean(forbidden),
                "answer_token_f1": statistics.mean(answer_f1),
            }
        )

    output_dir = ROOT / "benchmark" / "results"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "latest.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    summary = ["# Результат benchmark", ""]
    summary.extend(
        f"- {name}: {value:.4f}" if isinstance(value, float) else f"- {name}: {value}"
        for name, value in results.items()
    )
    (output_dir / "summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2))

    failed = (
        results["high_risk_recall"] < 1.0
        or results["high_risk_false_negatives"] != 0
        or results["auto_close_precision"] < 0.98
        or results["hot_path_p95_ms"] >= 500
        or (
            args.live
            and (results["retrieval_recall_at_3"] < 0.90 or results["forbidden_fact_rate"] > 0)
        )
    )
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
