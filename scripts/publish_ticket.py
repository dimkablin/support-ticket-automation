from __future__ import annotations

import argparse

from support_automation.adapters import TEXT_FIELDS
from support_automation.environment import Settings
from support_automation.models import Channel
from support_automation.queueing import RabbitPublisher


def main() -> None:
    parser = argparse.ArgumentParser(description="Положить один обезличенный тикет в RabbitMQ")
    parser.add_argument("query")
    parser.add_argument("--channel", choices=[item.value for item in Channel], default="chat")
    parser.add_argument("--device", default="desktop")
    parser.add_argument("--provider", choices=["fake", "litellm"], default="fake")
    args = parser.parse_args()

    settings = Settings.from_env()
    channel = Channel(args.channel)
    payload = {"device": args.device, TEXT_FIELDS[channel]: args.query}
    with RabbitPublisher(settings.rabbitmq_url, settings.rabbitmq_max_length) as publisher:
        ticket_id = publisher.publish_ticket(channel.value, payload, args.provider)
    print(ticket_id)


if __name__ == "__main__":
    main()
