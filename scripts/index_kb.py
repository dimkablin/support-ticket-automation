from __future__ import annotations

import argparse
import os
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Загрузить русскую KB в LightRAG")
    parser.add_argument("--url", default=os.getenv("LIGHTRAG_BASE_URL", "http://localhost:9621"))
    parser.add_argument("--api-key", default=os.getenv("LIGHTRAG_API_KEY", ""))
    args = parser.parse_args()

    headers = {"X-API-Key": args.api_key}
    health = httpx.get(f"{args.url.rstrip('/')}/health", headers=headers, timeout=10)
    health.raise_for_status()
    for path in sorted((ROOT / "kb").glob("*.md")):
        response = httpx.post(
            f"{args.url.rstrip('/')}/documents/text",
            headers=headers,
            json={"text": path.read_text(encoding="utf-8"), "file_source": f"kb/{path.name}"},
            timeout=30,
        )
        if response.status_code == 409:
            print(f"Уже загружен: kb/{path.name}")
            continue
        response.raise_for_status()
        print(f"Отправлен на индексацию: kb/{path.name}")


if __name__ == "__main__":
    main()
