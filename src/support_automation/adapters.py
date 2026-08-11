from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import uuid4

from .models import Channel, Ticket

TEXT_FIELDS = {
    Channel.CHAT: "message",
    Channel.EMAIL: "body",
    Channel.WEB: "message",
    Channel.MOBILE: "message",
}


def normalize_ticket(
    channel: str, payload: Mapping[str, Any], ticket_id: str | None = None
) -> Ticket:
    """Нормализует четыре внешних формата в единый тикет."""
    try:
        parsed_channel = Channel(channel)
    except ValueError as error:
        raise ValueError(f"Неизвестный канал: {channel}") from error

    field = TEXT_FIELDS[parsed_channel]
    query = payload.get(field)
    if not isinstance(query, str) or not query.strip():
        raise ValueError(f"Поле {field!r} должно содержать текст")
    device = payload.get("device", "unknown")
    if not isinstance(device, str) or not device.strip():
        raise ValueError("Поле 'device' должно быть строкой")

    return Ticket(
        id=ticket_id or str(uuid4()),
        query=query.strip(),
        channel=parsed_channel,
        device=device.strip(),
        payload=dict(payload),
    )
