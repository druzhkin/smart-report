"""Bench — real Gemini 3 lineup on the same report."""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

from _bench_scenarios import bench_one
from orchestrator import load_report


async def main() -> None:
    path = Path("reports/_live_1776370125.json")
    report = load_report(path)
    candidates = [
        "google/gemini-2.5-flash",  # baseline
        "google/gemini-3-flash-preview",
        "google/gemini-3.1-flash-lite-preview",
        "google/gemini-3-pro-preview",
        "google/gemini-3.1-pro-preview",
    ]
    print(f"Source: {path}\n", flush=True)
    results = []
    for m in candidates:
        print(f">>> {m}", flush=True)
        r = await bench_one(m, report.goal, report.blocks, report.connections)
        results.append(r)
        print(json.dumps(r, ensure_ascii=False, indent=2), flush=True)
        print("", flush=True)

    print("\n=== SUMMARY ===", flush=True)
    header = f"{'MODEL':<46} {'STATUS':<6} {'TIME':<7} {'TOK_OUT':<8} {'$':<8} {'₽':<7} {'TRIAD':<6} {'VRDCT_LEN':<10}"
    print(header, flush=True)
    print("-" * len(header), flush=True)
    for r in results:
        q = r.get("quality", {})
        print(
            f"{r['model']:<46} "
            f"{r['status']:<6} "
            f"{r['elapsed_s']:<7} "
            f"{r['output_tokens']:<8} "
            f"{round(r['cost_usd'], 4):<8} "
            f"{round(r['cost_rub'], 2):<7} "
            f"{str(q.get('triad_complete', '-')):<6} "
            f"{str(q.get('verdict_len', '-')):<10}",
            flush=True,
        )

    out = Path("reports") / f"_bench_gemini3_{int(time.time())}.json"
    out.write_text(json.dumps({"source": str(path), "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nsaved: {out}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
