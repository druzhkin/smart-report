"""CLI entry point.

First pass:
    python cli.py "цель"

Second pass (загружает отчёт из JSON, модифицирует, сохраняет новый набор файлов):
    python cli.py --from-json path/to/report.json --deepen "Domain / Layer" --focus "..."
    python cli.py --from-json path/to/report.json --add-domain "Имя домена" [--layers "L1, L2, L3"]
    python cli.py --from-json path/to/report.json --connect "Domain A" "Domain B"
"""
from __future__ import annotations

import argparse
import asyncio
import re
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
from datetime import datetime
from pathlib import Path

from config import OUTPUT_DIR
from export import save_all
from llm import meter_snapshot, reset_meter
from orchestrator import (
    add_domain,
    connect_domains,
    deepen_cell,
    load_report,
    run_research,
)


def _log(event: str, message: str) -> None:
    t = time.strftime("%H:%M:%S")
    print(f"[{t}] [{event}] {message}", flush=True)


def _slugify(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE).strip().lower()
    text = re.sub(r"[\s_]+", "-", text)
    return text[:60] or "report"


def _make_stem(goal: str, suffix: str = "") -> str:
    base = f"{datetime.now():%Y%m%dT%H%M%S}-{_slugify(goal)}"
    return f"{base}-{suffix}" if suffix else base


async def _run_fresh(
    goal: str, stem: str | None, depth: str, question_type: str | None = None
) -> int:
    reset_meter()
    start = time.time()
    report = await run_research(
        goal, progress=_log, depth=depth, question_type_override=question_type
    )
    stem = stem or _make_stem(goal)
    paths = save_all(report, OUTPUT_DIR, stem=stem)
    _print_summary(start, report, paths)
    return 0


async def _run_deepen(report_path: Path, cell: str, focus: str, stem: str | None) -> int:
    reset_meter()
    start = time.time()
    report = load_report(report_path)
    report = await deepen_cell(report, cell, focus, progress=_log)
    stem = stem or _make_stem(report.goal, f"deepen-{_slugify(cell)}")
    paths = save_all(report, OUTPUT_DIR, stem=stem)
    _print_summary(start, report, paths)
    return 0


async def _run_add_domain(
    report_path: Path, domain: str, layers_hint: list[str] | None, stem: str | None
) -> int:
    reset_meter()
    start = time.time()
    report = load_report(report_path)
    report = await add_domain(report, domain, layers_hint=layers_hint, progress=_log)
    stem = stem or _make_stem(report.goal, f"adddomain-{_slugify(domain)}")
    paths = save_all(report, OUTPUT_DIR, stem=stem)
    _print_summary(start, report, paths)
    return 0


async def _run_connect(report_path: Path, a: str, b: str, stem: str | None) -> int:
    reset_meter()
    start = time.time()
    report = load_report(report_path)
    report = await connect_domains(report, a, b, progress=_log)
    stem = stem or _make_stem(report.goal, f"connect-{_slugify(a)}-{_slugify(b)}")
    paths = save_all(report, OUTPUT_DIR, stem=stem)
    _print_summary(start, report, paths)
    return 0


def _print_summary(start: float, report, paths) -> None:
    elapsed = time.time() - start
    print("\n=== ГОТОВО ===")
    print(f"Время: {elapsed:.1f}s")
    print(f"Блоков: {len(report.blocks)}")
    print(f"Связей: {len(report.connections)}")
    if report.block_headers:
        h = sum(1 for x in report.block_headers if x.priority == "high")
        m = sum(1 for x in report.block_headers if x.priority == "medium")
        l = sum(1 for x in report.block_headers if x.priority == "low")
        print(f"Приоритеты: 🔴 {h} / 🟡 {m} / 🟢 {l}")
    for k, p in paths.items():
        print(f"{k:>5}: {p}")
    snap = meter_snapshot()
    print(f"\n--- Стоимость прогона ---")
    print(f"Всего: {snap['total_rub']:.2f} ₽  (LLM-часть ${snap['total_usd']:.4f}, "
          f"{snap['total_calls']} вызовов, {snap['total_input']} in / {snap['total_output']} out tok)")
    for model, m in snap["per_model"].items():
        print(f"  {model}: ${m['usd']:.4f}  ({int(m['calls'])} calls, "
              f"{int(m['input'])} in / {int(m['output'])} out)")
    for prov, p in snap["per_provider"].items():
        print(f"  [{prov}] {p['credits']:.2f} ₽  ({int(p['calls'])} calls)")


def _parse_layers(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    return [x.strip() for x in raw.split(",") if x.strip()]


def main() -> int:
    p = argparse.ArgumentParser(description="Smart Report MVP")
    p.add_argument("goal", nargs="?", help="Цель исследования (для первого прогона)")
    p.add_argument("--from-json", type=Path, help="Путь к JSON предыдущего отчёта для второго прохода")
    p.add_argument("--deepen", help="Ячейка для углубления, формат 'Domain / Layer'")
    p.add_argument("--focus", help="Фокус углубления (обязательно с --deepen)")
    p.add_argument("--add-domain", dest="add_domain", help="Имя нового домена")
    p.add_argument("--layers", help="Подсказка по слоям для --add-domain, через запятую")
    p.add_argument(
        "--connect",
        nargs=2,
        metavar=("A", "B"),
        help="Два домена для прицельной бисоциации",
    )
    p.add_argument("--stem", help="Имя выходных файлов (без расширения)", default=None)
    p.add_argument(
        "--depth",
        choices=["light", "standard", "deep", "premium"],
        default="standard",
        help="Глубина прогона (действует только для первого прохода)",
    )
    p.add_argument(
        "--question-type",
        dest="question_type",
        choices=["factual", "predictive", "comparative", "causal", "normative", "exploratory"],
        default=None,
        help="Форсировать planner.question_type (для A/B детерминизма; только первый проход)",
    )
    args = p.parse_args()

    try:
        if args.deepen:
            if not args.from_json or not args.focus:
                p.error("--deepen требует --from-json и --focus")
            return asyncio.run(_run_deepen(args.from_json, args.deepen, args.focus, args.stem))
        if args.add_domain:
            if not args.from_json:
                p.error("--add-domain требует --from-json")
            return asyncio.run(
                _run_add_domain(
                    args.from_json, args.add_domain, _parse_layers(args.layers), args.stem
                )
            )
        if args.connect:
            if not args.from_json:
                p.error("--connect требует --from-json")
            a, b = args.connect
            return asyncio.run(_run_connect(args.from_json, a, b, args.stem))
        if not args.goal:
            p.error("Укажи цель (первый аргумент) либо используй --from-json с операцией")
        return asyncio.run(_run_fresh(args.goal, args.stem, args.depth, args.question_type))
    except KeyboardInterrupt:
        print("\n[aborted]", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
