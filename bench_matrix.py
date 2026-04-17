"""Backend-source benchmark matrix: how do different search backends compare per question type?

Runs N goals × M backend configs. Per-finding source_db attribution lets us see which
backend actually contributed usable evidence for each question archetype.

Usage:
    python bench_matrix.py                # default: 1 goal × 5 key configs (smoke)
    python bench_matrix.py --full         # full 3 goals × 11 configs matrix
    python bench_matrix.py --goals 0,2 --configs A,C,D,ALL
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
import traceback
from collections import Counter
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)


# Three question archetypes. Keep them short so light depth still exercises all domains.
GOALS = [
    # 0: RU market / consumer — the failing case from prod
    "За что готовы платить покупатели бизнес- и премиум-новостроек в Москве 2024-2025",
    # 1: macro / cross-country
    "Мировые тренды на рынке жилой недвижимости 2024-2026: цены, ипотека, спрос",
    # 2: technical / product
    "Как спроектировать аналитическую платформу для финтеха: архитектура, стек, сценарии",
]

# Trusted-source whitelist for Tavily F-variant. Mix of EN/RU business, regulators, consultancies.
TAVILY_WHITELIST = (
    "reuters.com,bloomberg.com,ft.com,economist.com,wsj.com,"
    "vedomosti.ru,rbc.ru,kommersant.ru,interfax.ru,tass.ru,"
    "knightfrank.com,savills.com,cbre.com,jll.com,colliers.com,"
    "ons.gov.uk,bls.gov,ecb.europa.eu,imf.org,worldbank.org,oecd.org,"
    "rosstat.gov.ru,cbr.ru,domrf.ru,minfin.gov.ru"
)


def _config_flags(
    pplx: bool = False, gptr: bool = False, tavily: bool = False,
    academic: bool = False, cheap: bool = False, whitelist: str = ""
) -> dict:
    return {
        "use_perplexity": pplx,
        "use_gpt_researcher": gptr,
        "use_tavily": tavily,
        "use_academic": academic,
        "use_cheap_web": cheap,
        "tavily_include_domains": whitelist,
    }


# 11 backend combinations we want to compare.
CONFIGS: dict[str, dict] = {
    "A":      _config_flags(pplx=True),
    "B":      _config_flags(cheap=True),
    "C":      _config_flags(gptr=True),
    "D":      _config_flags(academic=True),
    "F":      _config_flags(tavily=True, whitelist=TAVILY_WHITELIST),
    "A+D":    _config_flags(pplx=True, academic=True),
    "B+D":    _config_flags(cheap=True, academic=True),
    "C+D":    _config_flags(gptr=True, academic=True),
    "C+F":    _config_flags(gptr=True, tavily=True, whitelist=TAVILY_WHITELIST),
    "A+C":    _config_flags(pplx=True, gptr=True),
    "A+C+D":  _config_flags(pplx=True, gptr=True, academic=True),
    "ALL":    _config_flags(pplx=True, gptr=True, tavily=True, academic=True, cheap=True, whitelist=TAVILY_WHITELIST),
}

SMOKE_CONFIGS = ["A", "B", "C", "D", "ALL"]

OUT_DIR = Path("reports/bench_matrix")
OUT_DIR.mkdir(parents=True, exist_ok=True)
SUMMARY = OUT_DIR / "summary.json"


def _slug(text: str, max_len: int = 40) -> str:
    s = re.sub(r"[^\w\s-]", "", text.lower(), flags=re.UNICODE)
    s = re.sub(r"\s+", "-", s.strip())
    return s[:max_len].strip("-")


def _apply_config(cfg: dict) -> dict:
    """Mutate settings frozen-dataclass in-place. Returns previous values for restoration."""
    import config
    prev = {}
    for k, v in cfg.items():
        prev[k] = getattr(config.settings, k)
        object.__setattr__(config.settings, k, v)
    return prev


def _restore_config(prev: dict) -> None:
    import config
    for k, v in prev.items():
        object.__setattr__(config.settings, k, v)


def _source_db_histogram(report) -> dict[str, int]:
    h: Counter = Counter()
    for b in report.blocks:
        for f in b.findings:
            h[f.source_db or "untagged"] += 1
    return dict(h)


def _count_stats(report) -> dict:
    total = 0
    with_url = 0
    with_numbers = 0
    stypes: Counter = Counter()
    uniq_domains: set[str] = set()
    for b in report.blocks:
        for f in b.findings:
            total += 1
            stypes[f.source_type] += 1
            if f.source and (f.source.startswith("http") or f.source.startswith("10.")):
                with_url += 1
                m = re.search(r"https?://([^/]+)/?", f.source)
                if m:
                    uniq_domains.add(m.group(1).lower())
            if f.has_numbers:
                with_numbers += 1
    return {
        "findings": total,
        "with_url": with_url,
        "with_numbers": with_numbers,
        "source_types": dict(stypes),
        "unique_domains": len(uniq_domains),
    }


async def run_one(goal: str, config_name: str, cfg: dict) -> dict:
    prev = _apply_config(cfg)
    try:
        from evaluator import evaluate_report
        from export import to_json
        from llm import meter_snapshot, reset_meter
        from orchestrator import run_research

        reset_meter()
        t0 = time.time()
        label = f"{config_name}/{_slug(goal, 24)}"

        def prog(ev: str, msg: str) -> None:
            print(f"[{label}][{ev}] {msg}", flush=True)

        report = await run_research(goal, progress=prog, depth="light")
        elapsed = time.time() - t0
        cost = meter_snapshot()

        stem = f"{config_name}_{_slug(goal)}"
        (OUT_DIR / f"{stem}.json").write_text(to_json(report), encoding="utf-8")

        try:
            ev = await evaluate_report(report)
            ev_total = ev.get("total")
            ev_scores = {k: v.get("score") for k, v in (ev.get("scores") or {}).items()
                         if isinstance(v, dict) and "score" in v}
            ev_low = [c.get("name") for c in ev.get("low_scores", [])]
        except Exception as err:
            ev_total, ev_scores, ev_low = None, {}, [f"eval_failed: {err}"]

        stats = _count_stats(report)
        per_provider = {k: round(v.get("credits", 0), 2) for k, v in (cost.get("per_provider") or {}).items()}
        return {
            "config": config_name,
            "goal": goal,
            "flags": cfg,
            "elapsed_sec": round(elapsed, 1),
            "cost_rub": round(cost.get("total_rub", 0), 2),
            "cost_usd_llm": round(cost.get("total_usd", 0), 4),
            "per_provider_rub": per_provider,
            "blocks": len(report.blocks),
            "connections": len(report.connections),
            "exec_summary": bool(report.exec_summary),
            **stats,
            "source_db_histogram": _source_db_histogram(report),
            "eval_total": ev_total,
            "eval_scores": ev_scores,
            "eval_low": ev_low,
        }
    finally:
        _restore_config(prev)


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--full", action="store_true", help="Run all 3 goals × 11 configs (~3 hr)")
    p.add_argument("--goals", type=str, default="", help="Goal indices comma-separated, e.g. '0,2'")
    p.add_argument("--configs", type=str, default="", help="Config names comma-separated, e.g. 'A,C,D'")
    args = p.parse_args()

    if args.goals:
        goal_ids = [int(x) for x in args.goals.split(",")]
    elif args.full:
        goal_ids = list(range(len(GOALS)))
    else:
        goal_ids = [0]
    if args.configs:
        config_names = [c.strip() for c in args.configs.split(",") if c.strip() in CONFIGS]
    elif args.full:
        config_names = list(CONFIGS.keys())
    else:
        config_names = SMOKE_CONFIGS

    runs: list[dict] = []
    total = len(goal_ids) * len(config_names)
    print(f"\nPlan: {len(goal_ids)} goals × {len(config_names)} configs = {total} runs\n")

    idx = 0
    for gi in goal_ids:
        goal = GOALS[gi]
        for name in config_names:
            idx += 1
            cfg = CONFIGS[name]
            header = f"[{idx}/{total}] goal={gi} config={name}"
            print(f"\n{'='*80}\n{header}\n{goal}\n{cfg}\n{'='*80}")
            try:
                r = await run_one(goal, name, cfg)
            except Exception as err:
                r = {"config": name, "goal": goal, "error": str(err), "tb": traceback.format_exc()[:2000]}
            runs.append(r)
            SUMMARY.write_text(json.dumps(runs, ensure_ascii=False, indent=2), encoding="utf-8")
            if "error" in r:
                print(f"  FAILED: {r['error']}")
            else:
                print(f"  eval={r.get('eval_total')} cost={r.get('cost_rub')}₽ sec={r.get('elapsed_sec')}")
                print(f"  source_db: {r.get('source_db_histogram')}")

    print("\n=== SUMMARY ===")
    print(f"{'goal':<6} {'cfg':<10} {'eval':>5} {'₽':>7} {'sec':>5} {'cites':>6} {'num%':>5}")
    for r in runs:
        if "eval_total" not in r:
            continue
        goal_idx = GOALS.index(r["goal"]) if r["goal"] in GOALS else -1
        cites = r.get("with_url", 0)
        nums = r.get("with_numbers", 0)
        total_f = r.get("findings", 1) or 1
        print(
            f"{goal_idx:<6} {r['config']:<10} {str(r.get('eval_total')):>5} "
            f"{r.get('cost_rub', 0):>7.2f} {r.get('elapsed_sec', 0):>5.0f} "
            f"{cites:>6} {int(100*nums/total_f):>4}%"
        )
    print(f"\nFull results: {SUMMARY}")


if __name__ == "__main__":
    asyncio.run(main())
