"""Клиент модели: OpenAI Chat Completions (OpenAI, ProxyAPI, aiprimetech и другие
совместимые сервисы).

Весь провайдер спрятан здесь: бот и скрипты вызывают только AIClient.complete
и получают AIResult. Чтобы сменить провайдера (например, на GigaChat),
достаточно переписать этот модуль, сохранив complete и AIResult.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import openai
from openai import AsyncOpenAI

if TYPE_CHECKING:
    from config import Settings

log = logging.getLogger(__name__)

# finish_reason → короткие понятные значения для логов и таблиц
_FINISH_REASONS = {"stop": "end_turn", "length": "max_tokens", "content_filter": "content_filter",
                   "tool_calls": "tool_use"}


@dataclass(frozen=True)
class AIResult:
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    stop_reason: str | None
    latency_s: float
    request_id: str | None


class AIError(Exception):
    """Ошибка запроса к модели. user_message можно показывать пользователю."""

    def __init__(self, user_message: str, kind: str, status: int | None = None,
                 detail: str = "") -> None:
        super().__init__(f"{kind}: {detail or user_message}")
        self.user_message = user_message
        self.kind = kind
        self.status = status
        self.detail = detail


def _error_detail(exc: Exception) -> str:
    """Короткое описание ошибки от API (без заголовков и ключей)."""
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict) and err.get("message"):
            return str(err["message"])[:300]
        if body.get("message"):
            return str(body["message"])[:300]
    return str(getattr(exc, "message", "") or exc)[:300]


def _fail(user_message: str, kind: str, exc: Exception, detail: str = "") -> AIError:
    status = getattr(exc, "status_code", None)
    detail = detail or _error_detail(exc)
    log.error("AI error: kind=%s status=%s detail=%s", kind, status or "-", detail)
    return AIError(user_message, kind, status, detail)


def _translate(exc: Exception) -> AIError:
    if isinstance(exc, openai.APITimeoutError):
        return _fail("Модель не ответила вовремя. Попробуйте ещё раз или уменьшите max_tokens.",
                     "timeout", exc)
    if isinstance(exc, openai.APIConnectionError):
        return _fail("Нет связи с API модели. Проверьте интернет и OPENAI_BASE_URL.",
                     "connection", exc)
    if isinstance(exc, openai.RateLimitError):
        return _fail("Слишком много запросов или закончился лимит/баланс. Подождите минуту.",
                     "rate_limit", exc)
    if isinstance(exc, (openai.AuthenticationError, openai.PermissionDeniedError)):
        return _fail("Ключ API не принят: проверьте OPENAI_API_KEY и доступ к модели.", "auth", exc)
    if isinstance(exc, openai.NotFoundError):
        return _fail("Модель или адрес API не найдены: проверьте имя модели и OPENAI_BASE_URL.",
                     "not_found", exc)
    if isinstance(exc, openai.BadRequestError):
        detail = _error_detail(exc)
        return _fail(f"Запрос отклонён: {detail}", "bad_request", exc, detail)
    status = getattr(exc, "status_code", "?")
    return _fail(f"Ошибка API модели (код {status}). Попробуйте позже.", "api_error", exc)


class AIClient:
    def __init__(
        self,
        api_key: str = "",
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 60.0,
        client: Any | None = None,
        max_retries: int = 2,
        tokens_param: str = "max_completion_tokens",
    ) -> None:
        # max_retries: SDK сам повторит запрос при 429/5xx/обрыве соединения
        self._client = client or AsyncOpenAI(api_key=api_key, base_url=base_url,
                                             timeout=timeout, max_retries=max_retries)
        self._tokens_param = tokens_param

    @classmethod
    def from_settings(cls, settings: Settings, timeout: float | None = None,
                      max_retries: int = 2) -> AIClient:
        return cls(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            timeout=timeout or settings.request_timeout,
            max_retries=max_retries,
            tokens_param=settings.openai_tokens_param,
        )

    async def complete(
        self,
        messages: list[dict[str, str]],
        system: str | None,
        model: str,
        max_tokens: int,
        effort: str | None = None,
        temperature: float | None = None,
    ) -> AIResult:
        chat = ([{"role": "system", "content": system}] if system else []) + list(messages)
        kwargs: dict[str, Any] = {"model": model, "messages": chat, self._tokens_param: max_tokens}
        if effort:
            kwargs["reasoning_effort"] = effort
        if temperature is not None:
            kwargs["temperature"] = temperature

        # В лог — только параметры и размеры, без текстов сообщений
        log.info(
            "AI request: model=%s %s=%s effort=%s temperature=%s messages=%d system=%s",
            model, self._tokens_param, max_tokens, effort or "default",
            "-" if temperature is None else temperature, len(messages),
            "yes" if system else "no",
        )

        started = time.monotonic()
        try:
            response = await self._client.chat.completions.create(**kwargs)
        except openai.APIError as exc:
            raise _translate(exc) from exc

        choice = response.choices[0] if response.choices else None
        text = ((choice.message.content if choice and choice.message else "") or "").strip()
        finish = getattr(choice, "finish_reason", None) if choice else None
        usage = response.usage
        result = AIResult(
            text=text,
            model=getattr(response, "model", model) or model,
            input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(usage, "completion_tokens", 0) or 0,
            stop_reason=_FINISH_REASONS.get(finish, finish),
            latency_s=round(time.monotonic() - started, 2),
            request_id=getattr(response, "_request_id", None),
        )
        log.info(
            "AI response: model=%s in=%d out=%d stop=%s latency=%.2fs chars=%d request_id=%s",
            result.model, result.input_tokens, result.output_tokens, result.stop_reason,
            result.latency_s, len(text), result.request_id or "-",
        )
        return result

    async def list_models(self) -> list[str]:
        """Модели, доступные ключу (GET /v1/models)."""
        page = await self._client.models.list()
        return [getattr(item, "id", str(item)) async for item in page]

    async def close(self) -> None:
        close = getattr(self._client, "close", None)
        if close:
            await close()
