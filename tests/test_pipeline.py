from pathlib import Path

from support_automation.classifier import ThemeClassifier, load_rows
from support_automation.models import Action, RetrievedDocument
from support_automation.pipeline import FALLBACK_RESPONSE, TicketPipeline
from support_automation.privacy import mask_pii
from support_automation.providers import FakeLLM

ROOT = Path(__file__).resolve().parents[1]


class StaticKnowledge:
    def __init__(self, content: str) -> None:
        self.content = content

    def search(self, query: str, top_k: int = 3) -> list[RetrievedDocument]:
        return [RetrievedDocument("kb/payment_methods.md", self.content)]


def test_happy_path_risk_gate_and_fallback() -> None:
    classifier = ThemeClassifier.train(load_rows(ROOT / "data" / "query_dataset.jsonl"))
    content = (ROOT / "kb" / "payment_methods.md").read_text(encoding="utf-8")
    safe = TicketPipeline(classifier, StaticKnowledge(content), FakeLLM(), confidence_threshold=0)
    decision = safe.process(
        "email",
        {
            "device": "desktop",
            "from": "user@example.test",
            "subject": "Оплата",
            "body": "Какими способами можно оплатить подписку?",
        },
    )
    assert decision.action is Action.AUTO_CLOSE
    assert "СБП" in decision.response

    risky = safe.process(
        "chat",
        {"device": "ios", "message": "С карты дважды списали деньги"},
    )
    assert risky.high_risk is True
    assert risky.action is Action.HUMAN_REVIEW

    unavailable = TicketPipeline(classifier, StaticKnowledge(content), FakeLLM(fail=True))
    fallback = unavailable.process(
        "web",
        {"device": "mobile_web", "message": "Какими способами можно оплатить подписку?"},
    )
    assert fallback.action is Action.HUMAN_REVIEW
    assert fallback.response == FALLBACK_RESPONSE
    assert mask_pii("Карта 4111 1111 1111 1111, user@example.com") == "Карта [CARD], [EMAIL]"
