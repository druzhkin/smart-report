"""A/B bench: run same goal with Perplexity on vs off, at light depth tier.

Emits reports/ab_bench.json with eval scores, cost, source-type histogram.
"""
from __future__ import annotations

import asyncio
import io
import json
import sys
import time
import traceback
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

# Neutral goal: broad enough to exercise every domain, not tied to niche RU data.
GOAL = (
    "Как запускать SaaS-продукт в условиях высокой конкуренции: "
    "юнит-экономика, каналы приобретения клиентов, retention и ценообразование"
)

OUT = Path("reports/ab_bench.json")


async def run_once(use_pplx: bool, label: str) -> dict:
    import config
    # Mutate frozen dataclass via object.__setattr__
    object.__setattr__(config.settings, "use_perplexity", use_pplx)

    from evaluator import evaluate_report
    from export import to_json
    from llm import meter_snapshot, reset_meter
    from orchestrator import run_research

    reset_meter()
    t0 = time.time()

    def prog(ev: str, msg: str) -> None:
        print(f"[{label}][{ev}] {msg}", flush=True)

    report = await run_research(GOAL, progress=prog, depth="light")
    elapsed = time.time() - t0
    cost = meter_snapshot()

    Path("reports").mkdir(exist_ok=True)
    Path(f"reports/ab_{label}.json").write_text(to_json(report), encoding="utf-8")

    # Eval
    try:
        ev = await evaluate_report(report)
        ev_total = ev["total"]
        ev_scores = {
            k: v["score"] for k, v in ev["scores"].items()
            if isinstance(v, dict) and "score" in v
        }
        ev_low = [c["name"] for c in ev.get("low_scores", [])]
    except Exception as err:
        ev_total = None
        ev_scores = {}
        ev_low = [f"eval_failed: {err}"]

    # Source stats
    stypes: dict[str, int] = {}
    with_url = 0
    with_numbers = 0
    total = 0
    for b in report.blocks:
        for f in b.findings:
            total += 1
            stypes[f.source_type] = stypes.get(f.source_type, 0) + 1
            if f.source and (f.source.startswith("http") or f.source.startswith("10.")):
                with_url += 1
            if f.has_numbers:
                with_numbers += 1

    per_provider = cost.get("per_provider", {})
    return {
        "label": label,
        "use_perplexity": use_pplx,
        "elapsed_sec": round(elapsed, 1),
        "cost_rub": round(cost["total_rub"], 2),
        "cost_usd_llm": round(cost["total_usd"], 4),
        "per_provider_rub": {k: round(v.get("credits", 0), 2) for k, v in per_provider.items()},
        "total_findings": total,
        "source_types": stypes,
        "with_url": with_url,
        "with_numbers": with_numbers,
        "blocks": len(report.blocks),
        "connections": len(report.connections),
        "causal_chains": len(report.causal_chains),
        "pre_mortems": len(report.pre_mortems),
        "exec_summary_present": bool(report.exec_summary),
        "eval_total": ev_total,
        "eval_scores": ev_scores,
        "eval_low": ev_low,
    }


async def main() -> None:
    results: list[dict] = []
    for use_pplx, label in [(False, "nopplx"), (True, "pplx")]:
        print(f"\n{'='*80}\nRUN {label}  use_perplexity={use_pplx}\n{'='*80}")
        try:
            r = await run_once(use_pplx, label)
        except Exception as err:
            r = {"label": label, "error": str(err), "tb": traceback.format_exc()}
        results.append(r)
        OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n--- {label} result ---\n{json.dumps(r, ensure_ascii=False, indent=2)}\n")

    # Compact delta summary
    if len(results) == 2 and all("eval_total" in r for r in results):
        no, yes = results[0], results[1]
        print("\n=== DELTA (nopplx vs pplx) ===")
        print(f"  total:    {no.get('eval_total')}  vs  {yes.get('eval_total')}")
        print(f"  cost$:    {no.get('cost_usd'):.3f}  vs  {yes.get('cost_usd'):.3f}")
        print(f"  findings: {no.get('total_findings')}  vs  {yes.get('total_findings')}")
        print(f"  conns:    {no.get('connections')}  vs  {yes.get('connections')}")


if __name__ == "__main__":
    asyncio.run(main())
