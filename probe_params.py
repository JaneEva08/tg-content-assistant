"""Проба: какие параметры реально принимают модели, доступные ключу.

Уроки записаны давно, а API меняется. Скрипт отправляет каждой модели
несколько коротких дешёвых запросов и записывает, что принято, а что нет.

Запуск:  python probe_params.py
         python probe_params.py --list            — только список моделей
         python probe_params.py --models gpt-6-luna --out results/probe_luna.md
Результат: results/probe.md (+ вывод в консоль)
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import datetime
from pathlib import Path

from api_client import AIClient, AIError
from config import BASE_DIR, ConfigError, load_settings

PROMPT = [{"role": "user", "content": "Ответь одним словом: какого цвета небо ясным днём?"}]

# (название проверки, параметры запроса, что ожидаем)
CASES = [
    ("базовый запрос", {"max_tokens": 50}, "ответ"),
    ("temperature=0.2", {"max_tokens": 50, "temperature": 0.2}, "принят или 400"),
    ("temperature=1.0", {"max_tokens": 50, "temperature": 1.0}, "принят или 400"),
    ("effort=low", {"max_tokens": 50, "effort": "low"}, "принят или 400"),
    ("effort=high", {"max_tokens": 50, "effort": "high"}, "принят или 400"),
    ("max_tokens=3", {"max_tokens": 3}, "stop_reason=max_tokens"),
]


async def probe(models: list[str]) -> str:
    settings = load_settings(require_bot=False)
    # Для пробы — короткий таймаут и без повторов: сбой должен быть виден сразу
    client = AIClient.from_settings(settings, timeout=20, max_retries=0)
    endpoint = (f"`{settings.openai_base_url}` — OpenAI Chat Completions "
                f"(`/chat/completions`, лимит через `{settings.openai_tokens_param}`)")
    print(f"Проверяю связь и список моделей…\n  {endpoint}", flush=True)
    lines: list[str] = [
        f"# Проба параметров — {datetime.now():%d.%m.%Y %H:%M}",
        "",
        f"API: {endpoint}",
        "",
    ]

    try:
        try:
            ids = await client.list_models()
            lines += ["## Модели, доступные ключу (GET /v1/models)", ""]
            lines += [f"- `{i}`" for i in ids] or ["- (список пуст)"]
            print(f"  модели ключа: {', '.join(ids) or '(пусто)'}", flush=True)
        except Exception as exc:  # noqa: BLE001 — сервис может не отдавать список
            lines += ["## Модели, доступные ключу", "", f"Список не получен: {exc.__class__.__name__}"]
            print(f"  список моделей не получен: {exc.__class__.__name__}", flush=True)
        lines += ["", "## Результаты", "",
                  "| Модель | Проверка | Итог | stop_reason | Токены in/out | Время, с | Ответ API |",
                  "|---|---|---|---|---|---|---|"]

        total = len(models) * len(CASES)
        step = 0
        for model in models:
            for name, params, _expected in CASES:
                step += 1
                print(f"[{step}/{total}] {model}: {name} … ", end="", flush=True)
                try:
                    r = await client.complete(messages=PROMPT, system=None, model=model, **params)
                    answer = r.text.replace("\n", " ")[:40] or "(пусто)"
                    lines.append(f"| {model} | {name} | ✅ принят | {r.stop_reason} | "
                                 f"{r.input_tokens}/{r.output_tokens} | {r.latency_s} | {answer} |")
                    print(f"✅ {r.latency_s} с", flush=True)
                except AIError as exc:
                    detail = (exc.detail or exc.user_message).replace("|", "/").replace("\n", " ")[:120]
                    lines.append(f"| {model} | {name} | ❌ {exc.kind} {exc.status or ''} | — | — | — | {detail} |")
                    print(f"❌ {exc.kind}: {detail}", flush=True)
                    if exc.kind in ("connection", "timeout", "auth") and step == 1:
                        # нет связи или ключ не принят — дальше проверять бессмысленно
                        lines.append("")
                        lines.append(f"Проба остановлена: {exc.user_message}")
                        return "\n".join(lines) + "\n"
    finally:
        await client.close()

    lines += ["", "Расшифровка: ✅ — модель приняла параметр; ❌ bad_request 400 — параметр отклонён."]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--models", help="через запятую; по умолчанию — AI_MODELS из .env")
    parser.add_argument("--out", default="results/probe.md", help="куда сохранить отчёт")
    parser.add_argument("--list", action="store_true", help="только список моделей, без запросов к ним")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    try:
        settings = load_settings(require_bot=False)
    except ConfigError as exc:
        raise SystemExit(f"Ошибка настройки: {exc}")
    models = [m.strip() for m in args.models.split(",")] if args.models else list(settings.available_models)
    if args.list:
        models = []

    report = asyncio.run(probe(models))
    out = BASE_DIR / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(report)
    print(f"Сохранено: {out.relative_to(BASE_DIR)}")


if __name__ == "__main__":
    main()
