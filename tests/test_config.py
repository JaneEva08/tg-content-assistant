import pytest

import config
from config import ConfigError, load_settings, parse_effort, parse_user_ids


@pytest.fixture
def env(monkeypatch):
    # не читаем настоящий .env разработчика
    monkeypatch.setattr(config, "load_dotenv", lambda *a, **k: None)
    for key in ("BOT_TOKEN", "ALLOWED_USER_IDS", "OPENAI_API_KEY", "OPENAI_BASE_URL",
                "OPENAI_TOKENS_PARAM", "AI_MODEL", "AI_MODELS", "AI_MAX_TOKENS", "AI_EFFORT",
                "CONTEXT_MAX_MESSAGES", "CHANNEL_FILE"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("BOT_TOKEN", "123:abc")
    monkeypatch.setenv("OPENAI_API_KEY", "key")
    monkeypatch.setenv("ALLOWED_USER_IDS", "111, 222")
    return monkeypatch


def test_parse_user_ids():
    assert parse_user_ids("1, 2;3,,") == {1, 2, 3}
    with pytest.raises(ConfigError):
        parse_user_ids("abc")


def test_parse_effort():
    assert parse_effort("") is None
    assert parse_effort("HIGH") == "high"
    with pytest.raises(ConfigError):
        parse_effort("turbo")


def test_defaults(env):
    s = load_settings()
    assert s.allowed_user_ids == {111, 222}
    assert s.default_model == "gpt-6-astra"
    assert s.default_max_tokens == 1000
    assert s.context_max_messages == 20
    assert s.openai_tokens_param == "max_completion_tokens"


def test_models_from_env(env):
    env.setenv("AI_MODELS", "gpt-6-luna, gpt-6-astra")
    s = load_settings()
    assert s.available_models == ("gpt-6-luna", "gpt-6-astra")
    assert s.default_model == "gpt-6-luna"


def test_bot_refuses_to_start_without_allowed_users(env):
    env.setenv("ALLOWED_USER_IDS", "")
    with pytest.raises(ConfigError):
        load_settings()
    assert load_settings(require_bot=False).allowed_user_ids == frozenset()


def test_bad_tokens_param(env):
    env.setenv("OPENAI_TOKENS_PARAM", "tokens")
    with pytest.raises(ConfigError):
        load_settings()


def test_missing_key_error_does_not_leak_anything(env):
    env.setenv("OPENAI_API_KEY", "")
    with pytest.raises(ConfigError) as info:
        load_settings()
    assert "OPENAI_API_KEY" in str(info.value)
