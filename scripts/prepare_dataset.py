from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "banking_requests.csv"
OUT = ROOT / "data" / "query_dataset.jsonl"
KB = ROOT / "kb"

HIGH_RISK_THEMES = {"duplicate_charge", "fraud_suspected", "refund_missing", "payment_dispute"}

THEMES = {
    "payment_methods": {
        "title": "Доступные способы оплаты",
        "answer": "Оплатить подписку можно банковской картой или через СБП. Наличные и переводы по реквизитам не поддерживаются.",
        "facts": ["банковская карта", "СБП"],
        "templates": [
            "Какими способами можно оплатить подписку{suffix}?",
            "Подскажите доступные варианты оплаты{suffix}",
            "Можно ли оплатить сервис через СБП{suffix}?",
            "Какие карты принимаются для оплаты{suffix}?",
            "Хочу узнать, как оплатить подписку{suffix}",
        ],
    },
    "pricing": {
        "title": "Стоимость подписки",
        "answer": "Базовая подписка стоит 499 рублей в месяц. Итоговая цена показывается до подтверждения оплаты.",
        "facts": ["499 рублей", "месяц"],
        "templates": [
            "Сколько стоит базовая подписка{suffix}?",
            "Какая цена тарифа на месяц{suffix}?",
            "Подскажите стоимость подписки{suffix}",
            "Сколько я заплачу за базовый план{suffix}?",
            "Где посмотреть цену перед оплатой{suffix}?",
        ],
    },
    "invoice_download": {
        "title": "Скачивание чека",
        "answer": "Чек доступен в разделе «Платежи»: откройте нужную операцию и нажмите «Скачать чек».",
        "facts": ["Платежи", "Скачать чек"],
        "templates": [
            "Где скачать чек об оплате{suffix}?",
            "Мне нужен чек за подписку{suffix}",
            "Как получить документ о платеже{suffix}?",
            "Не могу найти чек в приложении{suffix}",
            "Подскажите путь к чеку операции{suffix}",
        ],
    },
    "subscription_cancel": {
        "title": "Отключение продления",
        "answer": "Автопродление отключается в разделе «Подписка» → «Управление» → «Отключить продление». Доступ сохранится до конца оплаченного периода.",
        "facts": ["Отключить продление", "до конца оплаченного периода"],
        "templates": [
            "Как отключить автопродление{suffix}?",
            "Хочу отменить подписку{suffix}",
            "Где прекратить продление тарифа{suffix}?",
            "После отмены доступ сразу исчезнет{suffix}?",
            "Помогите выключить следующее списание{suffix}",
        ],
    },
    "password_reset": {
        "title": "Восстановление доступа",
        "answer": "На экране входа нажмите «Забыли пароль?», укажите подтверждённый email и перейдите по ссылке из письма. Код или пароль сотруднику сообщать нельзя.",
        "facts": ["Забыли пароль", "email"],
        "source_label": "APP_LOGIN",
    },
    "verification_help": {
        "title": "Помощь с проверкой личности",
        "answer": "Откройте «Профиль» → «Проверка личности» и загрузите читаемые фотографии документа. Решение принимает служба проверки; поддержка не может гарантировать одобрение.",
        "facts": ["Проверка личности", "фотографии документа"],
        "source_label": "KYC_VERIFICATION",
    },
    "technical_issue": {
        "title": "Техническая диагностика приложения",
        "answer": "Обновите приложение, перезапустите устройство и повторите действие в стабильной сети. Если ошибка сохранится, передайте оператору версию приложения и время сбоя.",
        "facts": ["обновите приложение", "версию приложения"],
        "source_label": "APP_TECH",
    },
    "service_unavailable": {
        "title": "Недоступность сервиса",
        "answer": "Проверьте статус сервиса и повторите попытку позже. Если массовый инцидент подтверждён, тикет связывается с инцидентом и передаётся оператору без повторной диагностики.",
        "facts": ["статус сервиса", "инцидентом"],
        "templates": [
            "Сервис сейчас не открывается{suffix}",
            "У вас массовый сбой{suffix}?",
            "Приложение пишет, что сервер недоступен{suffix}",
            "Ничего не работает уже несколько минут{suffix}",
            "Не могу подключиться к сервису{suffix}",
        ],
    },
    "duplicate_charge": {
        "title": "Повторное списание",
        "answer": "Не обещайте возврат автоматически. Сверьте идентификаторы операций и передайте обращение оператору платёжной линии.",
        "facts": ["идентификаторы операций", "оператору"],
        "templates": [
            "С карты дважды списали деньги{suffix}",
            "Вижу повторное списание за подписку{suffix}",
            "Почему один платёж прошёл два раза{suffix}?",
            "Верните второе списание{suffix}",
            "Сумма оплаты задублировалась{suffix}",
        ],
    },
    "fraud_suspected": {
        "title": "Подозрение на мошенничество",
        "answer": "Не подтверждайте операцию и не запрашивайте секретные данные. Передайте тикет оператору линии безопасности и рекомендуйте пользователю заблокировать карту через банк.",
        "facts": ["оператору линии безопасности", "заблокировать карту"],
        "source_label": "FRAUD_SUSPECTED",
    },
    "refund_missing": {
        "title": "Не поступил возврат",
        "answer": "Не называйте срок без проверки операции. Передайте тикет оператору платёжной линии с датой, суммой и идентификатором возврата.",
        "facts": ["оператору", "идентификатором возврата"],
        "source_label": "INCOMING_DELAY",
    },
    "payment_dispute": {
        "title": "Спорная исходящая операция",
        "answer": "Не отменяйте и не подтверждайте спорную операцию автоматически. Передайте тикет оператору платёжной линии для проверки статуса и реквизитов.",
        "facts": ["оператору платёжной линии", "проверки статуса"],
        "source_label": "PAYMENT_OUT_FAIL",
    },
}

SUFFIXES = ["", " сегодня", " в приложении", " на сайте", " для моего аккаунта"]
CHANNELS = ["chat", "email", "web", "mobile"]
DEVICES = ["desktop", "ios", "android", "mobile_web"]


def source_queries() -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    try:
        text = RAW.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        text = RAW.read_text(encoding="cp1251")
    for row in csv.DictReader(text.splitlines(), delimiter=";"):
        grouped.setdefault(row["label"], []).append(row["text"].strip())
    assert {"APP_LOGIN", "APP_TECH", "KYC_VERIFICATION", "FRAUD_SUSPECTED"} <= grouped.keys()
    return grouped


def payload(channel: str, device: str, query: str, number: int) -> dict[str, str]:
    common = {"device": device}
    if channel == "email":
        return {
            **common,
            "from": f"user{number}@example.test",
            "subject": "Обращение в поддержку",
            "body": query,
        }
    if channel == "web":
        return {**common, "form_id": "support", "message": query}
    if channel == "mobile":
        return {**common, "app_version": "1.0.0", "message": query}
    return {**common, "session_id": f"demo-{number:03d}", "message": query}


def main() -> None:
    sources = source_queries()
    rows: list[dict[str, object]] = []
    KB.mkdir(parents=True, exist_ok=True)

    for theme_index, (theme, config) in enumerate(THEMES.items()):
        document_id = f"kb/{theme}.md"
        risk = theme in HIGH_RISK_THEMES
        audience = "Внутренняя инструкция" if risk else "Публичная справка"
        document = (
            f"# {config['title']}\n\n"
            f"Тип: {audience}.\n\n"
            f"Тема: `{theme}`.\n\n"
            f"## Проверенный ответ\n\n{config['answer']}\n\n"
            f"## Обязательные факты\n\n" + "\n".join(f"- {fact}" for fact in config["facts"]) + "\n"
        )
        kb_path = KB / f"{theme}.md"
        if not kb_path.exists():
            kb_path.write_text(document, encoding="utf-8")

        if "source_label" in config:
            queries = sources[str(config["source_label"])][:25]
        else:
            templates = config["templates"]
            queries = [
                str(templates[index % len(templates)]).format(
                    suffix=SUFFIXES[index // len(templates)]
                )
                for index in range(25)
            ]

        for index, query in enumerate(queries):
            number = theme_index * 25 + index + 1
            channel = CHANNELS[(number - 1) % 4]
            device = DEVICES[(number - 1) % 4]
            split = "train" if index < 15 else "development" if index < 20 else "test"
            rows.append(
                {
                    "id": f"ticket-{number:03d}",
                    "query": query,
                    "theme": theme,
                    "answer": config["answer"],
                    "required_facts": config["facts"],
                    "forbidden_facts": [
                        "гарантируем возврат",
                        "сообщите пароль",
                        "назовите код из СМС",
                    ],
                    "high_risk": risk,
                    "expected_action": (
                        "human_need"
                        if risk
                        else "auto_reply"
                        if theme
                        in {
                            "payment_methods",
                            "pricing",
                            "invoice_download",
                            "subscription_cancel",
                        }
                        else "approve_require"
                    ),
                    "expected_document_id": document_id,
                    "channel": channel,
                    "device": device,
                    "source": "banking-requests-cc0"
                    if "source_label" in config
                    else "deterministic-template",
                    "split": split,
                    "payload": payload(channel, device, query, number),
                }
            )

    assert len(rows) == 300
    assert len({row["id"] for row in rows}) == 300
    assert all(sum(row["theme"] == theme for row in rows) == 25 for theme in THEMES)
    assert sum(row["high_risk"] for row in rows) == 100
    assert {row["expected_action"] for row in rows} == {
        "auto_reply",
        "approve_require",
        "human_need",
    }
    assert {row["expected_action"] for row in rows if row["high_risk"]} == {"human_need"}
    assert {
        split: sum(row["split"] == split for row in rows)
        for split in ("train", "development", "test")
    } == {"train": 180, "development": 60, "test": 60}

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
    )
    print(f"Создано {len(rows)} тикетов; KB содержит {len(THEMES)} документов")


if __name__ == "__main__":
    main()
