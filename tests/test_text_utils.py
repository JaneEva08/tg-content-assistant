import pytest

from text_utils import TELEGRAM_LIMIT, split_message


def test_short_text_is_single_chunk():
    assert split_message("  короткий пост  ") == ["короткий пост"]


def test_empty_text():
    assert split_message("   ") == []


def test_long_text_respects_limit_and_keeps_content():
    paragraph = "Абзац про тревогу и выгорание. " * 20
    text = "\n\n".join(paragraph.strip() for _ in range(30))
    chunks = split_message(text)
    assert len(chunks) > 1
    assert all(len(c) <= 4000 < TELEGRAM_LIMIT for c in chunks)
    assert "".join(chunks).replace(" ", "").replace("\n", "") == text.replace(" ", "").replace("\n", "")


def test_prefers_paragraph_boundaries():
    first = "а" * 60
    second = "б" * 60
    chunks = split_message(f"{first}\n\n{second}", limit=100)
    assert chunks == [first, second]


def test_single_huge_word_is_cut_hard():
    chunks = split_message("x" * 250, limit=100)
    assert [len(c) for c in chunks] == [100, 100, 50]


def test_tiny_limit_rejected():
    with pytest.raises(ValueError):
        split_message("текст", limit=5)
