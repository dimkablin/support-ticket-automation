from __future__ import annotations

from pathlib import Path
from typing import Protocol

import httpx

from .models import RetrievedDocument


class KnowledgeBase(Protocol):
    def search(self, query: str, top_k: int = 3) -> list[RetrievedDocument]: ...


class LightRAGClient:
    def __init__(self, base_url: str, api_key: str, timeout: float = 15.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.headers = {"X-API-Key": api_key}
        self.timeout = timeout

    def search(self, query: str, top_k: int = 3) -> list[RetrievedDocument]:
        response = httpx.post(
            f"{self.base_url}/query/data",
            headers=self.headers,
            json={"query": query, "mode": "mix", "top_k": top_k, "chunk_top_k": top_k},
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json().get("data") or {}
        documents: list[RetrievedDocument] = []
        seen: set[str] = set()
        for chunk in data.get("chunks") or []:
            file_path = str(chunk.get("file_path") or "unknown")
            document_id = f"kb/{Path(file_path).name}"
            if document_id in seen:
                continue
            seen.add(document_id)
            documents.append(
                RetrievedDocument(
                    document_id=document_id,
                    content=str(chunk.get("content") or ""),
                    score=float(chunk.get("score") or 0.0),
                )
            )
            if len(documents) >= top_k:
                break
        return documents
