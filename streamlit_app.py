from __future__ import annotations

import json

import streamlit as st

from support_automation.adapters import TEXT_FIELDS
from support_automation.bootstrap import build_pipeline
from support_automation.environment import Settings
from support_automation.models import Action, Channel

DEVICE_PROFILES: dict[str, tuple[Channel, dict[str, str]]] = {
    "Ноутбук · чат": (
        Channel.CHAT,
        {"device": "desktop", "session_id": "demo-chat-001"},
    ),
    "iPhone · email": (
        Channel.EMAIL,
        {
            "device": "ios",
            "from": "user@example.test",
            "subject": "Обращение в поддержку",
        },
    ),
    "Android · веб-форма": (
        Channel.WEB,
        {"device": "android", "form_id": "support"},
    ),
    "Мобильный браузер · приложение": (
        Channel.MOBILE,
        {"device": "mobile_web", "app_version": "1.0.0"},
    ),
}

EXAMPLES: dict[str, str | None] = {
    "FAQ — автоответ": "Какими способами можно оплатить подписку?",
    "Нужна проверка": "Письмо подтверждения почты приходит без рабочей ссылки",
    "Денежный риск": "С карты дважды списали деньги за одну подписку",
    "Свой текст": None,
}

st.set_page_config(page_title="Диспетчер тикетов", page_icon="🎫", layout="wide")
st.markdown(
    """
    <style>
    .stApp { background: var(--background-color); }
    .block-container { max-width: 1440px; padding-top: 2rem; }
    [data-testid="stVerticalBlockBorderWrapper"] {
        background: var(--secondary-background-color);
        border-color: color-mix(in srgb, var(--text-color) 16%, transparent);
        border-radius: 14px;
    }
    [data-testid="stMetricValue"] { font-size: 1.35rem; }
    @media (max-width: 900px) {
        [data-testid="stHorizontalBlock"] { display: block; }
        [data-testid="stColumn"] { width: 100% !important; margin-bottom: 1rem; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

settings = Settings.from_env()


@st.cache_resource
def pipeline(provider_name: str):
    return build_pipeline(settings, provider_name)


st.title("Демонстрация обработки тикетов")
st.caption(
    "Пользователь отправляет обращение с устройства, система классифицирует его, "
    "а оператор видит решение и следующий шаг."
)

with st.sidebar:
    st.header("Настройки демо")
    provider_name = st.radio(
        "Провайдер ответа",
        ["fake", "litellm"],
        format_func=lambda value: "FakeLLM" if value == "fake" else "LiteLLM",
    )
    st.caption("FakeLLM работает детерминированно; LiteLLM использует настроенный endpoint.")
    if st.button("Новый тикет", use_container_width=True):
        for key in (
            "decision",
            "submitted_payload",
            "submitted_query",
            "sent_response",
            "response_source",
            "submitted_provider",
        ):
            st.session_state.pop(key, None)
        st.rerun()

left, right = st.columns([0.92, 1.08], gap="large")

with left, st.container(border=True):
    st.subheader("Пользователь")
    st.caption("Сформируйте обращение так, как оно придёт из реального канала.")

    device_label = st.selectbox("Устройство и канал", list(DEVICE_PROFILES))
    example_label = st.selectbox("Сообщение", list(EXAMPLES))
    preset = EXAMPLES[example_label]
    if preset is None:
        query = st.text_area(
            "Текст обращения",
            placeholder="Опишите проблему своими словами…",
            height=130,
        )
    else:
        query = st.text_area(
            "Текст обращения",
            value=preset,
            height=130,
            disabled=True,
            key=f"preset-{example_label}",
        )

    channel, metadata = DEVICE_PROFILES[device_label]
    payload = {**metadata, TEXT_FIELDS[channel]: query.strip()}
    with st.expander("Payload устройства"):
        st.code(json.dumps(payload, ensure_ascii=False, indent=2), language="json")

    if st.button(
        "Отправить в поддержку",
        type="primary",
        use_container_width=True,
        disabled=not query.strip(),
    ):
        try:
            with st.spinner("Тикет проходит классификацию и маршрутизацию…"):
                decision = pipeline(provider_name).process(channel.value, payload)
        except Exception as error:  # noqa: BLE001 - UI показывает сбой окружения
            st.error(f"Тикет не обработан: {error}")
        else:
            st.session_state["decision"] = decision
            st.session_state["submitted_payload"] = payload
            st.session_state["submitted_query"] = query.strip()
            st.session_state["submitted_provider"] = provider_name
            st.session_state["sent_response"] = (
                decision.response if decision.action is Action.AUTO_REPLY else None
            )
            st.session_state["response_source"] = (
                "auto_reply" if decision.action is Action.AUTO_REPLY else None
            )
            st.rerun()

    submitted_query = st.session_state.get("submitted_query")
    if submitted_query:
        st.divider()
        st.caption("Диалог с поддержкой")
        with st.chat_message("user"):
            st.write(submitted_query)
        sent_response = st.session_state.get("sent_response")
        if sent_response:
            with st.chat_message("assistant"):
                st.write(sent_response)
        else:
            st.caption("Ответ ожидает действия оператора.")

with right, st.container(border=True):
    st.subheader("Рабочее место оператора")
    decision = st.session_state.get("decision")
    if decision is None:
        st.info("Отправьте тикет слева — здесь появятся классификация и действие.")
        st.markdown(
            "**Возможные маршруты**\n\n"
            "- `auto_reply` — проверенный ответ уже отправлен;\n"
            "- `need_approve` — оператор проверяет черновик;\n"
            "- `operator_reply` — оператор отвечает самостоятельно."
        )
    else:
        ui_state = {
            Action.AUTO_REPLY: "auto_reply",
            Action.APPROVE_REQUIRE: "need_approve",
            Action.HUMAN_NEED: "operator_reply",
        }[decision.action]

        if ui_state == "auto_reply":
            st.success("auto_reply · Ответ отправлен автоматически")
        elif ui_state == "need_approve":
            st.warning("need_approve · Черновик ждёт решения оператора")
        else:
            st.error("operator_reply · Автоответ запрещён")

        with st.chat_message("user"):
            st.write(decision.masked_query)

        metrics = st.columns(3)
        metrics[0].metric("Тема", decision.classification.theme)
        metrics[1].metric("Уверенность", f"{decision.classification.confidence:.0%}")
        metrics[2].metric("Задержка", f"{decision.latency_ms:.0f} мс")
        st.caption(
            f"Канал: {decision.channel} · Устройство: {decision.device} · "
            f"Денежный риск: {'да' if decision.high_risk else 'нет'}"
        )

        sent_response = st.session_state.get("sent_response")
        if sent_response:
            source = st.session_state.get("response_source")
            label = (
                "Система отправила ответ" if source == "auto_reply" else "Оператор отправил ответ"
            )
            st.success(label)
            with st.chat_message("assistant"):
                st.write(sent_response)
        elif ui_state == "need_approve":
            draft = st.text_area(
                "Черновик ответа",
                value=decision.response,
                height=150,
                key=f"draft-{decision.ticket_id}",
            )
            if st.button(
                "Одобрить и отправить",
                type="primary",
                use_container_width=True,
                disabled=not draft.strip(),
            ):
                # ponytail: operator actions stay in session until a real ticket backend exists.
                st.session_state["sent_response"] = draft.strip()
                st.session_state["response_source"] = "operator"
                st.rerun()
        else:
            st.caption(decision.response)
            operator_response = st.text_area(
                "Ответ оператора",
                placeholder="Напишите безопасный ответ пользователю…",
                height=150,
                key=f"operator-{decision.ticket_id}",
            )
            if st.button(
                "Отправить ответ оператора",
                type="primary",
                use_container_width=True,
                disabled=not operator_response.strip(),
            ):
                st.session_state["sent_response"] = operator_response.strip()
                st.session_state["response_source"] = "operator"
                st.rerun()

        with st.expander("Технические детали"):
            st.json(
                {
                    "ui_state": ui_state,
                    "provider": st.session_state.get("submitted_provider"),
                    "payload": st.session_state.get("submitted_payload"),
                    "top3": decision.classification.top3,
                    "document_id": decision.document_id,
                    "cache_hit": decision.cache_hit,
                    "trace_id": decision.trace_id,
                    "fallback_reason": decision.fallback_reason,
                }
            )
