from pathlib import Path

import pytest

from channel import ChannelError, build_system_prompt, load_channel

ROOT = Path(__file__).resolve().parent.parent


def test_example_channel_builds_prompt_with_rules_and_crisis_line():
    channel = load_channel(ROOT / "channel.example.yaml")
    prompt = build_system_prompt(channel)
    assert channel.name == "Точка опоры"
    assert "Не ставить диагнозы" in prompt
    assert "112" in prompt
    assert "без Markdown-разметки" in prompt
    assert "до 1500 знаков" in prompt
    for rule in channel.rules:
        assert rule in prompt


def test_missing_file(tmp_path):
    with pytest.raises(ChannelError):
        load_channel(tmp_path / "nope.yaml")


def test_name_required(tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text("tone: тёплый\n", encoding="utf-8")
    with pytest.raises(ChannelError):
        load_channel(path)


def test_empty_crisis_line_gets_placeholder(tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text("name: Тест\nrules: [без диагнозов]\n", encoding="utf-8")
    prompt = build_system_prompt(load_channel(path))
    assert "автор добавит вручную" in prompt
