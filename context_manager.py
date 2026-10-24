"""Контекст диалога каждого пользователя — в оперативной памяти.

После перезапуска бота история пропадает: для MVP этого достаточно.
"""

from __future__ import annotations

from collections import defaultdict

Message = dict[str, str]  # {"role": "user" | "assistant", "content": "..."}

ROLES = ("user", "assistant")


class ContextManager:
    def __init__(self, max_messages: int = 20) -> None:
        if max_messages < 2:
            raise ValueError("max_messages должен быть не меньше 2")
        self.max_messages = max_messages
        self._history: dict[int, list[Message]] = defaultdict(list)

    def get(self, user_id: int) -> list[Message]:
        """Копия истории — чтобы снаружи её нельзя было случайно испортить."""
        return [dict(m) for m in self._history.get(user_id, [])]

    def add(self, user_id: int, role: str, content: str) -> None:
        if role not in ROLES:
            raise ValueError(f"Неизвестная роль: {role}")
        self._history[user_id].append({"role": role, "content": content})
        self._trim(user_id)

    def add_user(self, user_id: int, content: str) -> None:
        self.add(user_id, "user", content)

    def add_assistant(self, user_id: int, content: str) -> None:
        self.add(user_id, "assistant", content)

    def rollback_last_user(self, user_id: int) -> None:
        """Убрать последнее сообщение пользователя, если запрос к модели не удался.

        Иначе после ошибки в истории окажутся два user-сообщения подряд,
        а модель «ответит» на вопрос, которого пользователь уже не видит.
        """
        history = self._history.get(user_id)
        if history and history[-1]["role"] == "user":
            history.pop()

    def reset(self, user_id: int) -> None:
        self._history.pop(user_id, None)

    def size(self, user_id: int) -> int:
        return len(self._history.get(user_id, []))

    def _trim(self, user_id: int) -> None:
        history = self._history[user_id]
        if len(history) > self.max_messages:
            del history[: len(history) - self.max_messages]
        # Диалог для Messages API должен начинаться с сообщения пользователя
        while history and history[0]["role"] != "user":
            history.pop(0)
