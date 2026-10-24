"""Настройки бота: всё берётся из .env, в коде секретов нет."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

# Уровни reasoning_effort для «думающих» моделей GPT
EFFORT_LEVELS = ("low", "medium", "high")

DEFAULT_MODELS = ("gpt-6-astra", "gpt-6-luna")
TOKENS_PARAMS = ("max_completion_tokens", "max_tokens")


class ConfigError(RuntimeError):
    """Понятная ошибка конфигурации — без значений секретов в тексте."""


@dataclass(frozen=True)
class Settings:
    bot_token: str
    openai_api_key: str
    openai_base_url: str
    openai_tokens_param: str
    allowed_user_ids: frozenset[int]
    default_model: str
    available_models: tuple[str, ...]
    default_max_tokens: int
    default_effort: str | None
    context_max_messages: int
    request_timeout: float
    channel_file: Path
    log_level: str


@dataclass
class UserParams:
    """Параметры запроса, которые пользователь меняет командами в боте."""

    model: str
    max_tokens: int
    effort: str | None = None
    temperature: float | None = None


def parse_user_ids(raw: str) -> frozenset[int]:
    ids: set[int] = set()
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        if not part.lstrip("-").isdigit():
            raise ConfigError(f"ALLOWED_USER_IDS: «{part}» — не число")
        ids.add(int(part))
    return frozenset(ids)


def parse_effort(raw: str | None) -> str | None:
    value = (raw or "").strip().lower()
    if value in ("", "default", "off", "none"):
        return None
    if value not in EFFORT_LEVELS:
        raise ConfigError(f"AI_EFFORT должен быть одним из: {', '.join(EFFORT_LEVELS)} или пустым")
    return value


def _int(name: str, default: int, low: int, high: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} должен быть целым числом") from exc
    if not low <= value <= high:
        raise ConfigError(f"{name} должен быть в диапазоне {low}–{high}")
    return value


def _resolve_channel_file() -> Path:
    raw = os.getenv("CHANNEL_FILE", "").strip()
    if raw:
        path = Path(raw)
        return path if path.is_absolute() else BASE_DIR / path
    private = BASE_DIR / "channel.yaml"  # свой профиль канала, в git не попадает
    return private if private.exists() else BASE_DIR / "channel.example.yaml"


def load_settings(require_bot: bool = True) -> Settings:
    """Читает .env. require_bot=False — для скриптов пробы и прогонов (без Telegram)."""
    load_dotenv(BASE_DIR / ".env")

    bot_token = os.getenv("BOT_TOKEN", "").strip()
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip().rstrip("/")
    tokens_param = os.getenv("OPENAI_TOKENS_PARAM", "max_completion_tokens").strip()

    if not api_key:
        raise ConfigError("Не задан OPENAI_API_KEY в .env")
    if tokens_param not in TOKENS_PARAMS:
        raise ConfigError(f"OPENAI_TOKENS_PARAM: {' или '.join(TOKENS_PARAMS)}")

    allowed: frozenset[int] = frozenset()
    if require_bot:
        if not bot_token:
            raise ConfigError("Не задан BOT_TOKEN в .env")
        allowed = parse_user_ids(os.getenv("ALLOWED_USER_IDS", ""))
        if not allowed:
            raise ConfigError(
                "ALLOWED_USER_IDS пуст: бот тратит ваш баланс, поэтому без списка не запустится. "
                "Свой Telegram ID можно узнать у @userinfobot"
            )

    models_raw = os.getenv("AI_MODELS", ",".join(DEFAULT_MODELS))
    models = tuple(m.strip() for m in models_raw.split(",") if m.strip()) or DEFAULT_MODELS
    default_model = os.getenv("AI_MODEL", models[0]).strip()

    try:
        timeout = float(os.getenv("AI_TIMEOUT", "60"))
    except ValueError as exc:
        raise ConfigError("AI_TIMEOUT должен быть числом (секунды)") from exc

    return Settings(
        bot_token=bot_token,
        openai_api_key=api_key,
        openai_base_url=base_url,
        openai_tokens_param=tokens_param,
        allowed_user_ids=allowed,
        default_model=default_model,
        available_models=models,
        default_max_tokens=_int("AI_MAX_TOKENS", 1000, 1, 32000),
        default_effort=parse_effort(os.getenv("AI_EFFORT")),
        context_max_messages=_int("CONTEXT_MAX_MESSAGES", 20, 2, 200),
        request_timeout=timeout,
        channel_file=_resolve_channel_file(),
        log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper(),
    )
