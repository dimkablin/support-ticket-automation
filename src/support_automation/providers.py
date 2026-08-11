from __future__ import annotations

import re
from typing import Protocol

import litellm


class LLMProvider(Protocol):
    name: str

    def generate(self, query: str, context: str) -> str: ...


class FakeLLM:
    name = "fake"

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    def generate(self, query: str, context: str) -> str:
        if self.fail:
            raise TimeoutError("Сымитирована недоступность LLM")
        match = re.search(r"## Проверенный ответ\s+(.+?)(?:\s+##|$)", context, re.DOTALL)
        return match.group(1).strip() if match else context.strip()


class LiteLLMProvider:
    name = "litellm"

    def __init__(self, model: str, api_base: str, api_key: str, timeout: float = 30.0) -> None:
        self.model = model
        self.api_base = api_base
        self.api_key = api_key
        self.timeout = timeout

    def generate(self, query: str, context: str) -> str:
        response = litellm.completion(
            model=self.model,
            api_base=self.api_base,
            api_key=self.api_key,
            timeout=self.timeout,
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": "Ответь по-русски только по проверенному контексту. Не обещай действий, которых нет в контексте.",
                },
                {"role": "user", "content": f"Тикет: {query}\n\nКонтекст:\n{context}"},
            ],
        )
        content = response.choices[0].message.content
        if not content:
            raise ValueError("LiteLLM вернул пустой ответ")
        return str(content).strip()
