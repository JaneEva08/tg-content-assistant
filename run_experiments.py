"""Прогоны для отчёта: одна задача — разные модели и параметры.

Запуск:  python run_experiments.py            — все прогоны из experiments.yaml
         python run_experiments.py --only R1,R5
         python run_experiments.py --dry-run  — показать план без запросов
Результат: results/runs.md, results/runs.csv, results/answers/<id>.md
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from api_client import AIClient, AIError
from channel import build_system_prompt, load_channel
from config import BASE_DIR, ConfigError, load_settings



@dataclass
class Run:
    id: str
    model: str
    max_tokens: int
    effort: str | None
    temperature: float | None
    system: str  # channel | none
    prompt: str
    note: str


def load_plan(path: Path) -> tuple[list[Run], dict[str, str]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    default_prompt = " ".join(str(data["default_prompt"]).split())
    runs = []
    for item in data["runs"]:
        system = str(item.get("system", "channel")).lower()
        if system not in ("channel", "none"):
            raise ValueError(f"{item['id']}: system должен быть channel или none")
        runs.append(Run(
            id=str(item["id"]),
            model=str(item["model"]),
            max_tokens=int(item.get("max_tokens", 1000)),
            effort=item.get("effort") or None,
            temperature=None if item.get("temperature") is None else float(item["temperature"]),
            system=system,
            prompt=" ".join(str(item.get("prompt") or default_prompt).split()),
            note=str(item.get("note", "")),
        ))
    return runs, dict(data.get("red_flags") or {})


def load_prices(path: Path) -> dict[str, dict[str, float]]:
    return (yaml.safe_load(path.read_text(encoding="utf-8")) or {}) if path.exists() else {}


def cost_usd(prices: dict[str, dict[str, float]], model: str, tin: int, tout: int) -> float | None:
    p = prices.get(model)
    if not p:
        return None
    return (tin * p["input"] + tout * p["output"]) / 1_000_000


def find_flags(text: str, red_flags: dict[str, str]) -> list[str]:
    return [name for name, pattern in red_flags.items() if re.search(pattern, text, re.IGNORECASE)]


def fmt_cost(value: float | None) -> str:
    return "—" if value is None else f"${value:.5f}"


async def execute(runs: list[Run], red_flags: dict[str, str], out_dir: Path) -> list[dict[str, Any]]:
    settings = load_settings(require_bot=False)
    channel = load_channel(settings.channel_file)
    system_prompt = build_system_prompt(channel)
    prices = load_prices(BASE_DIR / "prices.yaml")
    client = AIClient.from_settings(settings)
    answers_dir = out_dir / "answers"
    answers_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    try:
        for run in runs:
            print(f"→ {run.id}: {run.model}, max_tokens={run.max_tokens}, "
                  f"effort={run.effort or 'default'}, temperature={run.temperature}, system={run.system}")
            row: dict[str, Any] = {
                "id": run.id, "model": run.model, "effort": run.effort or "default",
                "temperature": "—" if run.temperature is None else run.temperature,
                "max_tokens": run.max_tokens, "system": run.system, "note": run.note,
            }
            try:
                r = await client.complete(
                    messages=[{"role": "user", "content": run.prompt}],
                    system=system_prompt if run.system == "channel" else None,
                    model=run.model, max_tokens=run.max_tokens,
                    effort=run.effort, temperature=run.temperature,
                )
                flags = find_flags(r.text, red_flags)
                row.update(status="ok", stop_reason=r.stop_reason, input_tokens=r.input_tokens,
                           output_tokens=r.output_tokens, latency_s=r.latency_s, chars=len(r.text),
                           cost_usd=cost_usd(prices, run.model, r.input_tokens, r.output_tokens),
                           flags=", ".join(flags) or "—", request_id=r.request_id or "—", error="")
                body = r.text
            except AIError as exc:
                row.update(status=f"error {exc.status or exc.kind}", stop_reason="—", input_tokens=0,
                           output_tokens=0, latency_s=0, chars=0, cost_usd=None, flags="—",
                           request_id="—", error=exc.detail or exc.user_message)
                body = f"ОШИБКА: {exc.detail or exc.user_message}"
            rows.append(row)

            (answers_dir / f"{run.id}.md").write_text(
                f"# {run.id} — {run.note}\n\n"
                f"- модель: {run.model}\n- max_tokens: {run.max_tokens}\n"
                f"- effort: {run.effort or 'default'}\n- temperature: {row['temperature']}\n"
                f"- профиль канала: {'да' if run.system == 'channel' else 'нет'}\n"
                f"- stop_reason: {row['stop_reason']}\n- токены in/out: {row['input_tokens']}/{row['output_tokens']}\n"
                f"- request_id: {row['request_id']}\n\n## Запрос\n\n{run.prompt}\n\n## Ответ\n\n{body}\n",
                encoding="utf-8",
            )
    finally:
        await client.close()
    return rows


def write_reports(rows: list[dict[str, Any]], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    fields = ["id", "model", "effort", "temperature", "max_tokens", "system", "status", "stop_reason",
              "input_tokens", "output_tokens", "cost_usd", "latency_s", "chars", "flags",
              "request_id", "note", "error"]
    with (out_dir / "runs.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields, delimiter=";")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fields})

    lines = [
        f"# Прогоны — {datetime.now():%d.%m.%Y %H:%M}", "",
        "Колонку «Эффект» заполняю вручную после чтения ответов в `results/answers/`.", "",
        "| № | Модель | effort | temperature | max_tokens | Профиль | Итог | stop_reason | "
        "Токены in/out | ≈ Стоимость | Время, с | Знаков | Флаги | Эффект | Что проверяли |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    total = 0.0
    for r in rows:
        total += r["cost_usd"] or 0
        status = "✅" if r["status"] == "ok" else f"❌ {r['status']}"
        lines.append(
            f"| {r['id']} | {r['model']} | {r['effort']} | {r['temperature']} | {r['max_tokens']} | "
            f"{'канал' if r['system'] == 'channel' else 'нет'} | {status} | {r['stop_reason']} | "
            f"{r['input_tokens']}/{r['output_tokens']} | {fmt_cost(r['cost_usd'])} | {r['latency_s']} | "
            f"{r['chars']} | {r['flags']} | … | {r['note']} |"
        )
    lines += ["", f"Итого ≈ {fmt_cost(total)} по ценам из `prices.yaml`.", ""]
    errors = [r for r in rows if r["status"] != "ok"]
    if errors:
        lines += ["## Ответы API на отклонённые запросы", ""]
        lines += [f"- **{r['id']}**: {r['error']}" for r in errors]
        lines.append("")
    (out_dir / "runs.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", help="id прогонов через запятую, например R1,R5")
    parser.add_argument("--plan", default="experiments.yaml")
    parser.add_argument("--out", help="папка результатов; по умолчанию results/ или results/<имя плана> для других планов")
    parser.add_argument("--dry-run", action="store_true", help="показать план без запросов к API")
    args = parser.parse_args()

    runs, red_flags = load_plan(BASE_DIR / args.plan)
    stem = Path(args.plan).stem.replace("experiments_", "")
    out_dir = BASE_DIR / (args.out or ("results" if stem == "experiments" else f"results/{stem}"))
    if args.only:
        wanted = {x.strip() for x in args.only.split(",")}
        runs = [r for r in runs if r.id in wanted]
    if args.dry_run:
        for r in runs:
            print(f"{r.id}: {r.model} max_tokens={r.max_tokens} effort={r.effort or 'default'} "
                  f"temperature={r.temperature} system={r.system} — {r.note}")
        return

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    try:
        rows = asyncio.run(execute(runs, red_flags, out_dir))
    except ConfigError as exc:
        raise SystemExit(f"Ошибка настройки: {exc}")
    write_reports(rows, out_dir)
    rel = out_dir.relative_to(BASE_DIR)
    print(f"\nГотово: {rel}/runs.md, {rel}/runs.csv, {rel}/answers/")


if __name__ == "__main__":
    main()
