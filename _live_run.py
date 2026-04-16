"""Live E2E run — direct invocation, no HTTP."""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

from orchestrator import run_research, save_report


def _progress(stage: str, message: str) -> None:
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {stage}: {message}", flush=True)


async def main() -> None:
    goal = sys.argv[1] if len(sys.argv) > 1 else "каков прогноз по ценам на премиум-новостройки в Москве на горизонте 18 месяцев"
    depth = sys.argv[2] if len(sys.argv) > 2 else "light"
    print(f"GOAL: {goal}\nDEPTH: {depth}\n", flush=True)
    t0 = time.time()
    report = await run_research(goal, progress=_progress, depth=depth)
    elapsed = time.time() - t0
    print(f"\nDONE in {elapsed:.1f}s", flush=True)

    out_json = Path("reports") / f"_live_{int(time.time())}.json"
    save_report(report, out_json)
    print(f"saved: {out_json}", flush=True)

    print("\n=== PIPELINE ASSERTIONS ===", flush=True)
    print(f"question_type: {report.matrix.question_type}", flush=True)
    print(f"blocks: {len(report.blocks)}", flush=True)
    print(f"connections: {len(report.connections)}", flush=True)
    print(f"pre_mortems: {len(report.pre_mortems)}", flush=True)
    print(f"causal_chains: {len(report.causal_chains)}", flush=True)
    print(f"scenario_cone: {'YES' if report.scenario_cone else 'NO'}", flush=True)
    print(f"assumption_inversions: {len(report.assumption_inversions)} blocks", flush=True)
    for bi in report.assumption_inversions:
        crit = sum(1 for i in bi.inversions if i.dependency == "critical")
        print(f"  {bi.block_cell}: {len(bi.inversions)} inversions ({crit} critical), unfalsifiable={bi.unfalsifiable_flag}", flush=True)

    print("\n=== ANALOGIES PER BLOCK ===", flush=True)
    for b in report.blocks:
        geos = [a.location for a in b.analogies if a.location]
        print(f"  {b.cell}: {len(b.analogies)} analogies, locations={geos}", flush=True)

    print("\n=== TOP FINDINGS (should NOT say '0 источников') ===", flush=True)
    if report.exec_summary:
        for tf in report.exec_summary.top_findings:
            print(f"  - {tf.headline}", flush=True)

    print("\n=== UNVERIFIED NUMERICS (should be strip-marked, not raw fake numbers) ===", flush=True)
    for b in report.blocks:
        if b.unverified_numerics:
            print(f"  {b.cell}: {b.unverified_numerics}", flush=True)
        if "[число удалено" in (b.summary or ""):
            print(f"  {b.cell}: strip-marker present in summary", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
