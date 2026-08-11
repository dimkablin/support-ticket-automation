import httpx

from support_automation.knowledge import EmbeddingClient, QdrantKnowledgeBase
from support_automation.models import RetrievedDocument


def test_hybrid_search_uses_dense_sparse_rrf(monkeypatch) -> None:
    requests = []

    def post(url, **kwargs):
        requests.append((url, kwargs.get("json")))
        request = httpx.Request("POST", url)
        if url.endswith("/embeddings"):
            texts = kwargs["json"]["input"]
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"index": index, "embedding": [0.1, 0.2]} for index, _ in enumerate(texts)
                    ]
                },
                request=request,
            )
        return httpx.Response(
            200,
            json={
                "result": {
                    "points": [
                        {
                            "score": 0.75,
                            "payload": {"document_id": "kb/payment.md", "content": "СБП"},
                        }
                    ]
                }
            },
            request=request,
        )

    def get(url, **kwargs):
        return httpx.Response(404, request=httpx.Request("GET", url))

    def put(url, **kwargs):
        requests.append((url, kwargs.get("json")))
        return httpx.Response(200, request=httpx.Request("PUT", url))

    monkeypatch.setattr(httpx, "post", post)
    monkeypatch.setattr(httpx, "get", get)
    monkeypatch.setattr(httpx, "put", put)
    knowledge = QdrantKnowledgeBase(
        "http://qdrant:6333",
        "support_kb",
        "",
        EmbeddingClient("http://embeddings:8081/v1", "rubert"),
        2,
    )

    knowledge.index_documents([RetrievedDocument("kb/payment.md", "Оплата по СБП")])
    documents = knowledge.search("оплата по СБП")

    collection = requests[0][1]
    point = requests[2][1]["points"][0]
    query = requests[4][1]
    assert collection["sparse_vectors"] == {"sparse": {}}
    assert set(point["vector"]) == {"dense", "sparse"}
    assert [item["using"] for item in query["prefetch"]] == ["dense", "sparse"]
    assert query["query"] == {"rrf": {}}
    assert documents[0].document_id == "kb/payment.md"
