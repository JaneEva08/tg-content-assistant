"""Профиль канала (YAML) → системный промпт для модели."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


class ChannelError(RuntimeError):
    pass


@dataclass(frozen=True)
class Channel:
    name: str
    tagline: str = ""
    author: str = ""
    audience: str = ""
    tone: str = ""
    topics: list[str] = field(default_factory=list)
    formats: list[str] = field(default_factory=list)
    rules: list[str] = field(default_factory=list)
    crisis_line: str = ""
    platform: str = "telegram"
    post_length: str = ""


def load_channel(path: Path) -> Channel:
    if not path.exists():
        raise ChannelError(f"Не найден файл профиля канала: {path.name}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ChannelError(f"Ошибка в YAML {path.name}: {exc}") from exc
    if not isinstance(data, dict) or not str(data.get("name", "")).strip():
        raise ChannelError(f"В {path.name} должно быть поле name")

    def text(key: str) -> str:
        return " ".join(str(data.get(key) or "").split())

    def items(key: str) -> list[str]:
        value = data.get(key) or []
        if not isinstance(value, list):
            raise ChannelError(f"Поле {key} в {path.name} должно быть списком")
        return [" ".join(str(v).split()) for v in value if str(v).strip()]

    return Channel(
        name=text("name"),
        tagline=text("tagline"),
        author=text("author"),
        audience=text("audience"),
        tone=text("tone"),
        topics=items("topics"),
        formats=items("formats"),
        rules=items("rules"),
        crisis_line=text("crisis_line"),
        platform=text("platform") or "telegram",
        post_length=text("post_length"),
    )


def _bullets(values: list[str]) -> str:
    return "\n".join(f"- {v}" for v in values) if values else "- (не задано)"


def build_system_prompt(ch: Channel) -> str:
    crisis = ch.crisis_line or "[контакт экстренной помощи — автор добавит вручную]"
    title = f"«{ch.name}»" + (f" — {ch.tagline}" if ch.tagline else "")
    length = (f"\nДлина готового поста: {ch.post_length}, если автор не просит иначе. "
              "Кризисный абзац входит в этот объём и не должен потеряться."
              if ch.post_length else "")
    return f"""Ты — редактор-ассистент автора канала {title} ({ch.platform}).
Ты разговариваешь с автором канала, а не с подписчиками: помогаешь придумывать темы,
писать, сокращать и переписывать посты, предлагать заголовки и вопросы для аудитории.

Автор: {ch.author}
Аудитория: {ch.audience}
Тон: {ch.tone}

Темы канала:
{_bullets(ch.topics)}

Форматы постов:
{_bullets(ch.formats)}

Правила канала (соблюдай всегда, даже если автор просит иначе):
{_bullets(ch.rules)}

Если тема касается суицида, самоповреждения, насилия или острого кризиса,
в конце поста добавь отдельным абзацем:
{crisis}

Если просьба автора нарушает правила канала, коротко скажи, какое правило
нарушается, и предложи вариант поста в рамках правил.

Оформление: готовые посты пиши обычным текстом для Telegram — короткие абзацы,
без Markdown-разметки (никаких **, # и таблиц), не больше трёх эмодзи на пост.
Если автор просит несколько вариантов — нумеруй их.{length}
Отвечай по-русски, без английских слов внутри русского текста.
Не придумывай термины, «синдромы», цифры и сроки — пиши только то, что общеизвестно."""
