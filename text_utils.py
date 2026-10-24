"""Нарезка длинных ответов: Telegram не принимает сообщения длиннее 4096 символов."""

from __future__ import annotations

TELEGRAM_LIMIT = 4096


def split_message(text: str, limit: int = 4000) -> list[str]:
    """Режет текст на части не длиннее limit, по возможности по абзацам и строкам."""
    if limit < 10:
        raise ValueError("limit слишком маленький")
    text = text.strip()
    chunks: list[str] = []
    while len(text) > limit:
        cut = -1
        for sep in ("\n\n", "\n", " "):
            pos = text.rfind(sep, 0, limit)
            if pos >= limit // 2:  # не режем слишком рано — иначе будет много мелких кусков
                cut = pos
                break
        if cut <= 0:
            cut = limit  # одно очень длинное «слово» — режем жёстко
        chunk = text[:cut].rstrip()
        if chunk:
            chunks.append(chunk)
        text = text[cut:].lstrip()
    if text:
        chunks.append(text)
    return chunks
