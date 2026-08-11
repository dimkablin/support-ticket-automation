from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from .models import Classification
from .policy import HIGH_RISK_THEMES

MONEY_SIGNAL = re.compile(
    r"\b(?:перевод\w*|списан\w*|возврат\w*|мошенн\w*|оплата\b)",
    re.IGNORECASE,
)


class ThemeClassifier:
    version = "tfidf-char-v1"

    def __init__(self, model: Pipeline) -> None:
        self.model = model

    @classmethod
    def train(cls, rows: list[dict[str, Any]]) -> ThemeClassifier:
        train = [row for row in rows if row["split"] == "train"]
        model = Pipeline(
            [
                ("tfidf", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=2)),
                (
                    "classifier",
                    LogisticRegression(class_weight="balanced", max_iter=1000, random_state=42),
                ),
            ]
        )
        model.fit([row["query"] for row in train], [row["theme"] for row in train])
        return cls(model)

    @classmethod
    def load(cls, path: Path) -> ThemeClassifier:
        return cls(joblib.load(path))

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.model, path)

    def predict(self, query: str) -> Classification:
        probabilities = self.model.predict_proba([query])[0]
        classes = self.model.classes_
        ranked = sorted(
            zip(classes, probabilities, strict=True), key=lambda item: item[1], reverse=True
        )
        # ponytail: safety re-ranking of the existing top-3; replace with calibrated ML after more labels.
        if ranked[0][0] not in HIGH_RISK_THEMES and MONEY_SIGNAL.search(query):
            risky = next((item for item in ranked[:3] if item[0] in HIGH_RISK_THEMES), None)
            if risky:
                ranked.remove(risky)
                ranked.insert(0, risky)
        return Classification(
            theme=str(ranked[0][0]),
            confidence=float(ranked[0][1]),
            top3=tuple((str(theme), float(score)) for theme, score in ranked[:3]),
        )


def load_rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
