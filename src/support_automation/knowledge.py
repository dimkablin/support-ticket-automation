from __future__ import annotations

from typing import Protocol
from urllib.parse import quote
from uuid import NAMESPACE_URL, uuid5

import httpx
from sklearn.feature_extraction.text import HashingVectorizer

from .models import RetrievedDocument


class KnowledgeBase(Protocol):
    def search(self, query: str, top_k: int = 3) -> list[RetrievedDocument]: ...


class BGEClient:
    def __init__(self, base_url: str, model: str, timeout: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def embed(self, texts: list[str]) -> list[list[float]]:
        response = httpx.post(
            f"{self.base_url}/embeddings",
            json={"model": self.model, "input": texts},
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = sorted(response.json()["data"], key=lambda item: item["index"])
        return [item["embedding"] for item in data]


class QdrantKnowledgeBase:
    def __init__(
        self,
        base_url: str,
        collection: str,
        api_key: str,
        embeddings: BGEClient,
        dimension: int = 1024,
        timeout: float = 15.0,
    ) -> None:
        self.collection_url = f"{base_url.rstrip('/')}/collections/{quote(collection, safe='')}"
        self.headers = {"api-key": api_key} if api_key else {}
        self.embeddings = embeddings
        self.dimension = dimension
        self.timeout = timeout
        self.lexical = HashingVectorizer(
            n_features=2**18,
            alternate_sign=False,
            norm="l2",
            ngram_range=(1, 2),
        )

    def _sparse(self, texts: list[str]) -> list[dict[str, list[float] | list[int]]]:
        matrix = self.lexical.transform(texts)
        return [
            {
                "indices": matrix.getrow(index).indices.tolist(),
                "values": matrix.getrow(index).data.tolist(),
            }
            for index in range(matrix.shape[0])
        ]

    def search(self, query: str, top_k: int = 3) -> list[RetrievedDocument]:
        dense = self.embeddings.embed([query])[0]
        sparse = self._sparse([query])[0]
        response = httpx.post(
            f"{self.collection_url}/points/query",
            headers=self.headers,
            json={
                "prefetch": [
                    {"query": dense, "using": "dense", "limit": max(top_k * 4, 10)},
                    {"query": sparse, "using": "sparse", "limit": max(top_k * 4, 10)},
                ],
                "query": {"rrf": {}},
                "limit": top_k,
                "with_payload": True,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        return [
            RetrievedDocument(
                document_id=str(point["payload"]["document_id"]),
                content=str(point["payload"]["content"]),
                score=float(point["score"]),
            )
            for point in response.json()["result"]["points"]
        ]

    def index_documents(self, documents: list[RetrievedDocument]) -> None:
        response = httpx.get(self.collection_url, headers=self.headers, timeout=self.timeout)
        if response.status_code == 404:
            response = httpx.put(
                self.collection_url,
                headers=self.headers,
                json={
                    "vectors": {"dense": {"size": self.dimension, "distance": "Cosine"}},
                    "sparse_vectors": {"sparse": {}},
                },
                timeout=self.timeout,
            )
        response.raise_for_status()

        texts = [document.content for document in documents]
        dense_vectors = self.embeddings.embed(texts)
        if any(len(vector) != self.dimension for vector in dense_vectors):
            raise ValueError(f"BGE-M3 должен вернуть dense-вектор размерности {self.dimension}")
        sparse_vectors = self._sparse(texts)
        response = httpx.put(
            f"{self.collection_url}/points?wait=true",
            headers=self.headers,
            json={
                "points": [
                    {
                        "id": str(uuid5(NAMESPACE_URL, document.document_id)),
                        "vector": {"dense": dense, "sparse": sparse},
                        "payload": {
                            "document_id": document.document_id,
                            "content": document.content,
                        },
                    }
                    for document, dense, sparse in zip(
                        documents, dense_vectors, sparse_vectors, strict=True
                    )
                ]
            },
            timeout=max(self.timeout, 60.0),
        )
        response.raise_for_status()
