from pathlib import Path

from support_automation.classifier import ThemeClassifier, load_rows

ROOT = Path(__file__).resolve().parents[1]


if __name__ == "__main__":
    classifier = ThemeClassifier.train(load_rows(ROOT / "data" / "query_dataset.jsonl"))
    classifier.save(ROOT / "models" / "theme_classifier.joblib")
    print("Модель сохранена в models/theme_classifier.joblib")
