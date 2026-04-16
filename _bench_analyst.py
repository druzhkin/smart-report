"""Bench analyst models on a fixed ScoutResult input (cached on first run)."""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

from pydantic import BaseModel, Field

from config import load_prompt, set_active_profile, depth_profile
from llm import call_json, meter_snapshot, reset_meter
from models import Analogy, Block, CellPlan, Finding, IndicatorWarning, ScoutResult
from orchestrator import load_report
from agents.scout import scout

SYSTEM = load_prompt("analyst")


class _AnalystPayload(BaseModel):
    summary: str
    findings: list[Finding]
    gaps: list[str]
    key_entities: list[str]
    assumptions: list[str]
    analogies: list[Analogy] = Field(default_factory=list)
    indicators: list[IndicatorWarning] = Field(default_factory=list)
    decision_point: str | None = None


async def _get_scout_inputs(report_path: Path, cache_path: Path) -> tuple[str, list[ScoutResult]]:
    if cache_path.exists():
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        return data["cell"], [ScoutResult(**sr) for sr in data["scout_results"]]

    set_active_profile(depth_profile("light"))
    report = load_report(report_path)
    plan = report.matrix.cell_plans[0]
    print(f"Re-running scout for cell: {plan.cell} ({len(plan.tasks)} tasks)", flush=True)
    results = await asyncio.gather(*(scout(t) for t in plan.tasks))
    cache_path.write_text(
        json.dumps(
            {"cell": plan.cell, "scout_results": [r.model_dump() for r in results]},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return plan.cell, list(results)


async def bench_analyst(model: str, cell: str, scout_results: list[ScoutResult]) -> dict:
    reset_meter()
    findings_blob = json.dumps(
        [
            {
                "task": sr.task.query_focus,
                "notes": sr.notes,
                "findings": [f.model_dump() for f in sr.findings],
            }
            for sr in scout_results
        ],
        ensure_ascii=False,
        indent=2,
    )
    user = (
        f"Ячейка матрицы: {cell}\n\n"
        "Материал от Scout'ов (несколько пачек по разным заданиям):\n"
        f"{findings_blob}\n\n"
        "Собери проработанный блок по контракту из system prompt. Только JSON."
    )
    t0 = time.time()
    status, err, block = "ok", None, None
    try:
        payload = await call_json(
            model=model, system=SYSTEM, user=user, schema=_AnalystPayload, temperature=0.35,
        )
        block = Block(
            cell=cell,
            summary=payload.summary,
            findings=payload.findings,
            gaps=payload.gaps,
            key_entities=payload.key_entities,
            assumptions=payload.assumptions,
            analogies=payload.analogies,
            indicators=payload.indicators,
            decision_point=payload.decision_point,
        )
    except Exception as e:
        status, err = "fail", f"{type(e).__name__}: {str(e)[:200]}"
    elapsed = round(time.time() - t0, 1)
    snap = meter_snapshot()
    result = {
        "model": model,
        "status": status,
        "elapsed_s": elapsed,
        "err": err,
        "input_tokens": snap["total_input"],
        "output_tokens": snap["total_output"],
        "cost_usd": snap["total_usd"],
        "cost_rub": snap["total_rub"],
        "calls": snap["total_calls"],
    }
    if block:
        result["quality"] = {
            "summary_len": len(block.summary or ""),
            "findings": len(block.findings),
            "with_numbers": sum(1 for f in block.findings if f.has_numbers),
            "with_quotes": sum(1 for f in block.findings if f.verbatim_quote),
            "gaps": len(block.gaps),
            "assumptions": len(block.assumptions),
            "analogies": len(block.analogies),
            "analogy_geos": [a.location for a in block.analogies if a.location],
            "indicators": len(block.indicators),
            "decision_point": bool(block.decision_point),
        }
    return result


async def main() -> None:
    report_path = Path("reports/_live_1776370125.json")
    cache = Path("reports/_bench_analyst_scout_cache.json")
    cell, scout_results = await _get_scout_inputs(report_path, cache)
    total_findings = sum(len(sr.findings) for sr in scout_results)
    print(f"\ncell: {cell}\nscout_tasks: {len(scout_results)}, total_findings: {total_findings}\n", flush=True)

    models = [
        "moonshotai/kimi-k2",
        "google/gemini-3-flash-preview",
        "google/gemini-2.5-flash",
        "deepseek/deepseek-chat-v3.1",
        "anthropic/claude-sonnet-4.6",
        "openai/gpt-5-mini",
    ]
    results = []
    for m in models:
        print(f">>> {m}", flush=True)
        r = await bench_analyst(m, cell, scout_results)
        results.append(r)
        print(json.dumps(r, ensure_ascii=False, indent=2), flush=True)
        print("", flush=True)

    print("\n=== SUMMARY (analyst) ===", flush=True)
    header = f"{'MODEL':<38} {'STATUS':<6} {'TIME':<7} {'$':<8} {'₽':<7} {'SUM_LEN':<8} {'FND':<4} {'NUM':<4} {'QUOTES':<6} {'GAPS':<4} {'ANAL':<4}"
    print(header, flush=True)
    print("-" * len(header), flush=True)
    for r in results:
        q = r.get("quality", {})
        print(
            f"{r['model']:<38} "
            f"{r['status']:<6} "
            f"{r['elapsed_s']:<7} "
            f"{round(r['cost_usd'], 4):<8} "
            f"{round(r['cost_rub'], 2):<7} "
            f"{str(q.get('summary_len', '-')):<8} "
            f"{str(q.get('findings', '-')):<4} "
            f"{str(q.get('with_numbers', '-')):<4} "
            f"{str(q.get('with_quotes', '-')):<6} "
            f"{str(q.get('gaps', '-')):<4} "
            f"{str(q.get('analogies', '-')):<4}",
            flush=True,
        )

    out = Path("reports") / f"_bench_analyst_{int(time.time())}.json"
    out.write_text(json.dumps({"cell": cell, "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nsaved: {out}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
