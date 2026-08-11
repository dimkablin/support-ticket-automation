from __future__ import annotations

from contextlib import AbstractContextManager
from types import TracebackType
from typing import Any, Self


class TicketTrace(AbstractContextManager["TicketTrace"]):
    """Тонкая обёртка: без ключей работает локально, с ключами пишет обязательный trace."""

    def __init__(
        self,
        name: str,
        masked_input: dict[str, Any],
        public_key: str,
        secret_key: str,
        base_url: str,
    ) -> None:
        self.trace_id: str | None = None
        self._client: Any = None
        self._context: Any = None
        self._span: Any = None
        self._name = name
        self._input = masked_input
        self._credentials = (public_key, secret_key, base_url)

    def __enter__(self) -> Self:
        public_key, secret_key, base_url = self._credentials
        if not public_key or not secret_key or "CHANGE_ME" in public_key + secret_key:
            return self
        try:
            from langfuse import Langfuse

            self._client = Langfuse(
                public_key=public_key,
                secret_key=secret_key,
                base_url=base_url,
            )
            self._context = self._client.start_as_current_observation(
                as_type="span", name=self._name, input=self._input
            )
            self._span = self._context.__enter__()
            self.trace_id = self._client.get_current_trace_id()
        except Exception:  # noqa: BLE001 - отсутствие observability не роняет тикет
            self._client = self._context = self._span = None
        return self

    def finish(self, output: dict[str, Any]) -> None:
        if self._span:
            self._span.update(output=output)

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        if self._context:
            self._context.__exit__(exc_type, exc_value, traceback)
        if self._client:
            self._client.flush()
        return False
