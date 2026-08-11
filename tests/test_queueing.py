from support_automation.models import Action
from support_automation.queueing import (
    DEAD_LETTER_EXCHANGE,
    DLQ,
    GENERATE_QUEUE,
    HUMAN_QUEUE,
    INCOMING_QUEUE,
    TicketEnvelope,
    delivery_attempt,
    queue_arguments,
    route_queue,
)


def test_queue_contract_masks_routes_and_retries() -> None:
    envelope = TicketEnvelope.from_payload(
        "chat",
        {"device": "ios", "message": "Карта 4111 1111 1111 1111, user@example.com"},
        provider="fake",
    )

    assert envelope.query == "Карта [CARD], [EMAIL]"
    assert TicketEnvelope.from_json(envelope.to_json()) == envelope
    assert route_queue(Action.AUTO_REPLY) == GENERATE_QUEUE
    assert route_queue(Action.APPROVE_REQUIRE) == GENERATE_QUEUE
    assert route_queue(Action.HUMAN_NEED) == HUMAN_QUEUE
    assert delivery_attempt(None) == 1
    assert delivery_attempt({"x-delivery-count": 1}) == 2
    assert delivery_attempt({"x-delivery-count": 2}) == 3

    arguments = queue_arguments(50_000)
    assert arguments == {
        "x-queue-type": "quorum",
        "x-max-length": 50_000,
        "x-overflow": "reject-publish",
        "x-delivery-limit": 3,
        "x-dead-letter-strategy": "at-least-once",
        "x-dead-letter-exchange": DEAD_LETTER_EXCHANGE,
        "x-dead-letter-routing-key": DLQ,
    }
    assert {INCOMING_QUEUE, GENERATE_QUEUE, HUMAN_QUEUE, DLQ} == {
        "tickets.incoming",
        "tickets.generate",
        "tickets.human",
        "tickets.dlq",
    }
