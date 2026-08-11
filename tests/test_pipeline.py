from pathlib import Path

from support_automation.classifier import ThemeClassifier, load_rows
from support_automation.environment import Settings
from support_automation.models import Action, RetrievedDocument
from support_automation.pipeline import FALLBACK_RESPONSE, HUMAN_NEED_RESPONSE, TicketPipeline
from support_automation.privacy import mask_pii
from support_automation.providers import FakeLLM

ROOT = Path(__file__).resolve().parents[1]


class StaticKnowledge:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls = 0

    def search(self, query: str, top_k: int = 3) -> list[RetrievedDocument]:
        self.calls += 1
        return [RetrievedDocument("kb/payment_methods.md", self.content)]


class CountingFakeLLM(FakeLLM):
    def __init__(self, fail: bool = False) -> None:
        super().__init__(fail)
        self.calls = 0

    def generate(self, query: str, context: str) -> str:
        self.calls += 1
        return super().generate(query, context)


def test_three_routes_and_fallback() -> None:
    assert Settings.from_env().root == ROOT
    classifier = ThemeClassifier.train(load_rows(ROOT / "data" / "query_dataset.jsonl"))
    content = (ROOT / "kb" / "payment_methods.md").read_text(encoding="utf-8")
    knowledge = StaticKnowledge(content)
    provider = CountingFakeLLM()
    safe = TicketPipeline(classifier, knowledge, provider, confidence_threshold=0)
    decision = safe.process(
        "email",
        {
            "device": "desktop",
            "from": "user@example.test",
            "subject": "Оплата",
            "body": "Какими способами можно оплатить подписку?",
        },
    )
    assert decision.action is Action.AUTO_REPLY
    assert "СБП" in decision.response

    password_query = next(
        row["query"]
        for row in load_rows(ROOT / "data" / "query_dataset.jsonl")
        if row["theme"] == "password_reset"
    )
    approval = safe.process("chat", {"device": "desktop", "message": password_query})
    assert approval.action is Action.APPROVE_REQUIRE

    risky = safe.process(
        "chat",
        {"device": "ios", "message": "С карты дважды списали деньги"},
    )
    assert risky.high_risk is True
    assert risky.action is Action.HUMAN_NEED
    assert risky.response == HUMAN_NEED_RESPONSE
    assert risky.document_id is None
    assert knowledge.calls == 2
    assert provider.calls == 2

    unavailable = TicketPipeline(classifier, StaticKnowledge(content), FakeLLM(fail=True))
    fallback = unavailable.process(
        "web",
        {"device": "mobile_web", "message": "Какими способами можно оплатить подписку?"},
    )
    assert fallback.action is Action.HUMAN_NEED
    assert fallback.response == FALLBACK_RESPONSE
    assert mask_pii("Карта 4111 1111 1111 1111, user@example.com") == "Карта [CARD], [EMAIL]"
