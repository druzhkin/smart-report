"""Bench: scenarios agent on 4 models. Input = saved Report JSON."""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

from pydantic import BaseModel

from config import load_prompt
from llm import call_json, meter_snapshot, reset_meter
from models import Block, Connection, ScenarioCone
from orchestrator import load_report

SYSTEM = load_prompt("scenarios")


class _Payload(BaseModel):
    scenario_cone: ScenarioCone


def _user_prompt(goal: str, blocks: list[Block], connections: list[Connection]) -> str:
    blocks_compact = [
        {
            "cell": b.cell,
            "summary_excerpt": (b.summary or "")[:1000],
            "key_entities": b.key_entities,
            "strong_findings": [
                {"claim": f.claim, "source_label": f.source_label, "numeric_values": f.numeric_values}
                for f in b.findings if f.has_numbers
            ][:5],
            "indicators": [
                {"hypothesis": iw.hypothesis, "indicator": iw.indicator, "timeframe": iw.timeframe}
                for iw in (b.indicators or [])
            ],
        }
        for b in blocks
    ]
    connections_compact = [
        {"domains": c.domains, "nature": c.nature, "description": c.description, "novelty": c.novelty}
        for c in connections
    ]
    return (
        f"Цель исследования (предсказательный вопрос): {goal}\n\n"
        f"Блоки:\n{json.dumps(blocks_compact, ensure_ascii=False, indent=2)}\n\n"
        f"Связи:\n{json.dumps(connections_compact, ensure_ascii=False, indent=2)}\n\n"
        "Построй Конус правдоподобных будущих по контракту ScenarioCone. "
        "Верни JSON с единственным ключом scenario_cone."
    )


def _parse_probability(s: str) -> float:
    import re
    nums = re.findall(r"\d+", s)
    if not nums:
        return 0.0
    if len(nums) >= 2:
        return (float(nums[0]) + float(nums[1])) / 2
    return float(nums[0])


def _score(cone: ScenarioCone) -> dict:
    sc = cone.scenarios
    probs = [_parse_probability(s.probability) for s in sc]
    prob_sum = round(sum(probs), 1)
    has_three = len(sc) == 3
    has_names = {s.name.lower() for s in sc}
    has_base = any("base" in n or "базов" in n for n in has_names)
    has_opt = any("opt" in n or "оптим" in n for n in has_names)
    has_pes = any("pes" in n or "песс" in n for n in has_names)
    implications_avg = round(sum(len(s.implications) for s in sc) / max(len(sc), 1), 1)
    indicators_avg = round(sum(len(s.indicators) for s in sc) / max(len(sc), 1), 1)
    has_wild = cone.wild_card is not None
    has_verdict = bool(cone.conditional_verdict and len(cone.conditional_verdict) > 30)
    uncertainties = len(cone.key_uncertainties)
    return {
        "scenario_count": len(sc),
        "prob_sum": prob_sum,
        "triad_complete": has_three and has_base and has_opt and has_pes,
        "implications_avg": implications_avg,
        "indicators_avg": indicators_avg,
        "wild_card": has_wild,
        "verdict_len": len(cone.conditional_verdict or ""),
        "verdict_ok": has_verdict,
        "uncertainties": uncertainties,
    }


async def bench_one(model: str, goal: str, blocks: list[Block], connections: list[Connection]) -> dict:
    reset_meter()
    t0 = time.time()
    status = "ok"
    err = None
    cone = None
    try:
        payload = await call_json(
            model=model,
            system=SYSTEM,
            user=_user_prompt(goal, blocks, connections),
            schema=_Payload,
            temperature=0.5,
        )
        cone = payload.scenario_cone
    except Exception as e:
        status = "fail"
        err = f"{type(e).__name__}: {str(e)[:200]}"
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
    if cone:
        result["quality"] = _score(cone)
        result["verdict_sample"] = (cone.conditional_verdict or "")[:200]
    return result


async def main() -> None:
    import glob
    report_path = sys.argv[1] if len(sys.argv) > 1 else sorted(glob.glob("reports/_live_*.json"))[-1]
    report = load_report(Path(report_path))
    print(f"Source report: {report_path}", flush=True)
    print(f"  goal: {report.goal}", flush=True)
    print(f"  question_type: {report.matrix.question_type}", flush=True)
    print(f"  blocks: {len(report.blocks)} | connections: {len(report.connections)}\n", flush=True)

    models = [
        "google/gemini-2.5-flash",
        "deepseek/deepseek-chat-v3.1",
        "anthropic/claude-sonnet-4.6",
        "openai/gpt-5-mini",
    ]
    results = []
    for m in models:
        print(f">>> {m}", flush=True)
        r = await bench_one(m, report.goal, report.blocks, report.connections)
        results.append(r)
        print(json.dumps(r, ensure_ascii=False, indent=2), flush=True)
        print("", flush=True)

    print("\n=== SUMMARY ===", flush=True)
    header = f"{'MODEL':<38} {'STATUS':<6} {'TIME':<7} {'TOK_OUT':<8} {'$':<8} {'₽':<7} {'TRIAD':<6} {'WILD':<5} {'VRDCT':<5}"
    print(header, flush=True)
    print("-" * len(header), flush=True)
    for r in results:
        q = r.get("quality", {})
        print(
            f"{r['model']:<38} "
            f"{r['status']:<6} "
            f"{r['elapsed_s']:<7} "
            f"{r['output_tokens']:<8} "
            f"{round(r['cost_usd'], 4):<8} "
            f"{round(r['cost_rub'], 2):<7} "
            f"{str(q.get('triad_complete', '-')):<6} "
            f"{str(q.get('wild_card', '-')):<5} "
            f"{str(q.get('verdict_ok', '-')):<5}",
            flush=True,
        )

    out = Path("reports") / f"_bench_scenarios_{int(time.time())}.json"
    out.write_text(json.dumps({"source": report_path, "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nsaved: {out}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
