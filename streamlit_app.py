from __future__ import annotations

from typing import Any

import streamlit as st

from support_automation.bootstrap import build_pipeline
from support_automation.classifier import load_rows
from support_automation.environment import Settings

st.set_page_config(page_title="Автоматизация тикетов", page_icon="🎫", layout="wide")
settings = Settings.from_env()
rows = load_rows(settings.root / "data" / "query_dataset.jsonl")


@st.cache_resource
def pipeline(provider_name: str):
    return build_pipeline(settings, provider_name)


st.title("Автоматизация тикетов поддержки")
st.caption("Русскоязычный PoC: быстрый классификатор, денежный risk gate, LightRAG и аудит")

left, right = st.columns(2)
with left:
    channel = st.selectbox("Канал", ["chat", "email", "web", "mobile"])
    device = st.selectbox("Устройство", ["desktop", "ios", "android", "mobile_web"])
with right:
    theme = st.selectbox("Тема примера", sorted({row["theme"] for row in rows}))
    provider_name = st.radio("Провайдер ответа", ["fake", "litellm"], horizontal=True)

examples = [row for row in rows if row["theme"] == theme]
example = st.selectbox(
    "Готовый пример — вручную вводить не нужно",
    examples,
    format_func=lambda row: row["query"],
)

if st.button("Обработать тикет", type="primary"):
    payload: dict[str, Any] = {"device": device, "message": example["query"]}
    if channel == "email":
        payload = {
            "device": device,
            "from": "demo@example.test",
            "subject": "Поддержка",
            "body": example["query"],
        }
    try:
        decision = pipeline(provider_name).process(channel, payload, example["id"])
    except Exception as error:  # noqa: BLE001 - UI показывает ошибку окружения
        st.error(f"Не удалось запустить окружение: {error}")
    else:
        status = "Автозакрытие" if decision.action.value == "auto_close" else "Проверка оператором"
        st.subheader(status)
        a, b, c, d = st.columns(4)
        a.metric("Тема", decision.classification.theme)
        b.metric("Уверенность", f"{decision.classification.confidence:.1%}")
        c.metric("Денежный риск", "Да" if decision.high_risk else "Нет")
        d.metric("Задержка", f"{decision.latency_ms:.0f} мс")
        st.write(decision.response)
        st.json(
            {
                "top3": decision.classification.top3,
                "document_id": decision.document_id,
                "cache_hit": decision.cache_hit,
                "trace_id": decision.trace_id,
                "fallback_reason": decision.fallback_reason,
                "masked_query": decision.masked_query,
            }
        )
