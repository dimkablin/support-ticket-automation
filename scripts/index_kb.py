from __future__ import annotations

from pathlib import Path

from support_automation.environment import Settings
from support_automation.knowledge import BGEClient, QdrantKnowledgeBase
from support_automation.models import RetrievedDocument

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    settings = Settings.from_env()
    paths = sorted((ROOT / "kb").glob("*.md"))
    knowledge = QdrantKnowledgeBase(
        settings.qdrant_url,
        settings.qdrant_collection,
        settings.qdrant_api_key,
        BGEClient(settings.bge_m3_url, settings.bge_m3_model),
        settings.bge_m3_dim,
    )
    knowledge.index_documents(
        [RetrievedDocument(f"kb/{path.name}", path.read_text(encoding="utf-8")) for path in paths]
    )
    print(f"Загружено документов в Qdrant: {len(paths)}")


if __name__ == "__main__":
    main()
