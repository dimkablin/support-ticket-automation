from __future__ import annotations

from .models import Action, Classification

HIGH_RISK_THEMES = frozenset(
    {"duplicate_charge", "fraud_suspected", "refund_missing", "payment_dispute"}
)
AUTO_CLOSE_THEMES = frozenset(
    {
        "payment_methods",
        "pricing",
        "invoice_download",
        "subscription_cancel",
    }
)


def decide_action(
    classification: Classification, confidence_threshold: float = 0.22
) -> tuple[bool, Action]:
    high_risk = classification.theme in HIGH_RISK_THEMES
    if high_risk or classification.confidence < confidence_threshold:
        return high_risk, Action.HUMAN_REVIEW
    if classification.theme in AUTO_CLOSE_THEMES:
        return False, Action.AUTO_CLOSE
    return False, Action.HUMAN_REVIEW
