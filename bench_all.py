"""3-way bench: nopplx (no tavily) | nopplx+tavily | pplx.

Toggles settings.use_perplexity and settings.tavily_api_key at runtime.
Emits reports/bench_all.json.
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
import traceback
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

GOAL = (
    "Как запускать SaaS-продукт в условиях высокой конкуренции: "
    "юнит-экономика, каналы приобретения клиентов, retention и ценообразование"
)

OUT = Path("reports/bench_all.json")


async def run_once(use_pplx: bool, use_tavily: bool, label: str, saved_tavily_key: str) -> dict:
    import config
    object.__setattr__(config.settings, "use_perplexity", use_pplx)
    object.__setattr__(
        config.settings,
        "tavily_api_key",
        saved_tavily_key if use_tavily else "",
    )

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
    Path(f"reports/bench_{label}.json").write_text(to_json(report), encoding="utf-8")

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
        "use_tavily": use_tavily,
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
    import config
    saved = config.settings.tavily_api_key

    variants = [
        (False, False, "nopplx"),
        (False, True, "nopplx_tavily"),
        (True, False, "pplx"),
    ]

    results: list[dict] = []
    for use_pplx, use_tav, label in variants:
        print(f"\n{'='*80}\nRUN {label}  pplx={use_pplx} tavily={use_tav}\n{'='*80}")
        try:
            r = await run_once(use_pplx, use_tav, label, saved)
        except Exception as err:
            r = {"label": label, "error": str(err), "tb": traceback.format_exc()}
        results.append(r)
        OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n--- {label} result ---\n{json.dumps(r, ensure_ascii=False, indent=2)}\n")

    print("\n=== SUMMARY ===")
    print(f"{'variant':<20} {'eval':>6} {'rub':>8} {'sec':>6}  {'providers (₽)'}")
    for r in results:
        if "eval_total" in r:
            prov = json.dumps(r.get("per_provider_rub", {}), ensure_ascii=False)
            print(
                f"{r['label']:<20} {str(r.get('eval_total')):>6} "
                f"{r.get('cost_rub', 0):>8.2f} {r.get('elapsed_sec', 0):>6.0f}  {prov}"
            )


if __name__ == "__main__":
    asyncio.run(main())
