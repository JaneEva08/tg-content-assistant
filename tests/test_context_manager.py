import pytest

from context_manager import ContextManager


def test_add_and_get_returns_copy():
    ctx = ContextManager(10)
    ctx.add_user(1, "привет")
    history = ctx.get(1)
    history.append({"role": "user", "content": "чужая правка"})
    history[0]["content"] = "изменено снаружи"
    assert ctx.get(1) == [{"role": "user", "content": "привет"}]


def test_users_are_isolated():
    ctx = ContextManager(10)
    ctx.add_user(1, "a")
    ctx.add_user(2, "b")
    assert ctx.get(1) == [{"role": "user", "content": "a"}]
    assert ctx.get(2) == [{"role": "user", "content": "b"}]


def test_trim_keeps_last_messages_and_starts_with_user():
    ctx = ContextManager(4)
    for i in range(5):
        ctx.add_user(1, f"q{i}")
        ctx.add_assistant(1, f"a{i}")
    history = ctx.get(1)
    assert len(history) <= 4
    assert history[0]["role"] == "user"
    assert history[-1] == {"role": "assistant", "content": "a4"}


def test_trim_with_odd_limit_drops_leading_assistant():
    ctx = ContextManager(3)
    for i in range(3):
        ctx.add_user(1, f"q{i}")
        ctx.add_assistant(1, f"a{i}")
    history = ctx.get(1)
    assert history[0]["role"] == "user"
    assert [m["content"] for m in history] == ["q2", "a2"]


def test_reset_and_size():
    ctx = ContextManager(10)
    ctx.add_user(1, "a")
    ctx.add_assistant(1, "b")
    assert ctx.size(1) == 2
    ctx.reset(1)
    assert ctx.size(1) == 0
    assert ctx.get(1) == []
    ctx.reset(999)  # сброс пустого контекста не падает


def test_rollback_removes_only_trailing_user_message():
    ctx = ContextManager(10)
    ctx.add_user(1, "q")
    ctx.add_assistant(1, "a")
    ctx.rollback_last_user(1)  # последнее — ответ модели, его не трогаем
    assert ctx.size(1) == 2
    ctx.add_user(1, "q2")
    ctx.rollback_last_user(1)
    assert ctx.get(1)[-1]["content"] == "a"


def test_invalid_role_and_limit():
    ctx = ContextManager(10)
    with pytest.raises(ValueError):
        ctx.add(1, "system", "нельзя")
    with pytest.raises(ValueError):
        ContextManager(1)
