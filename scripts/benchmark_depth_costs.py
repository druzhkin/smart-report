from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]

import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.v2.intake import build_request_spec, build_task_spec
from backend.v2.pipeline import build_draft_run, execute_report_run
from backend.v2.repository import FileRunRepository


async def _emit_noop(_event) -> None:
    return None


def _write_results(output_path: Path, latest_path: Path, results: list[dict]) -> None:
    payload = json.dumps(results, ensure_ascii=False, indent=2)
    output_path.write_text(payload, encoding="utf-8")
    latest_path.write_text(payload, encoding="utf-8")


async def _run_one(query: str, depth: str, decision_context: str) -> dict:
    run_id = f"depth-benchmark-{depth}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    repo = FileRunRepository(
        root=str(ROOT / "tmp" / "depth_benchmarks" / "runs"),
        reports_root=str(ROOT / "tmp" / "depth_benchmarks" / "reports"),
    )
    request_spec = build_request_spec(query, depth=depth)
    task_spec = build_task_spec(
        request_spec,
        answers={"decision-context": decision_context},
        output_formats=["html"],
        allow_perplexity_handoff=False,
    )
    summary = build_draft_run(run_id, query, depth=depth)
    summary.task_spec = task_spec
    repo.create_run(summary)
    started_at = perf_counter()
    final_summary = await execute_report_run(repo, summary, task_spec, _emit_noop)
    duration_seconds = round(perf_counter() - started_at, 2)

    spend_breakdown = [item.model_dump(mode="json") for item in final_summary.spend_breakdown]
    spend_by_stage: dict[str, float] = {}
    for entry in final_summary.spend_breakdown:
        spend_by_stage[entry.stage] = round(spend_by_stage.get(entry.stage, 0.0) + entry.cost_usd, 6)

    return {
        "run_id": final_summary.run_id,
        "depth": depth,
        "status": final_summary.status.value,
        "cost_usd": final_summary.cost_usd,
        "tokens_used": final_summary.tokens_used,
        "release_status": final_summary.audit_summary.release_status if final_summary.audit_summary else None,
        "coverage_ratio": final_summary.coverage_report.coverage_ratio if final_summary.coverage_report else None,
        "quality_score": final_summary.quality_assessment.overall_score if final_summary.quality_assessment else None,
        "duration_seconds": duration_seconds,
        "spend_by_stage": spend_by_stage,
        "spend_breakdown": spend_breakdown,
        "report_urls": final_summary.report_url_map,
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark real depth spend across light/standard/deep/exhaustive.")
    parser.add_argument("--query", required=True, help="Query to benchmark.")
    parser.add_argument(
        "--decision-context",
        default="Choose the default workflow and justify when to switch to an alternative.",
        help="Decision context injected into the task spec.",
    )
    parser.add_argument(
        "--depths",
        nargs="+",
        default=["light", "standard", "deep", "exhaustive"],
        choices=["light", "standard", "deep", "exhaustive"],
        help="Depth tiers to execute.",
    )
    args = parser.parse_args()

    output_dir = ROOT / "reports" / "evals"
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    output_path = output_dir / f"depth_benchmark_{timestamp}.json"
    latest_path = output_dir / "depth_benchmark_latest.json"

    results = []
    for depth in args.depths:
        try:
            results.append(await _run_one(args.query, depth, args.decision_context))
        except Exception as exc:
            results.append(
                {
                    "depth": depth,
                    "status": "failed",
                    "error": str(exc),
                }
            )
        _write_results(output_path, latest_path, results)

    print(json.dumps({"output_path": str(output_path), "results": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
