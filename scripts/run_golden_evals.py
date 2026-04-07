from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.chdir(ROOT)

from backend.v2.intake import build_clarification_pack, build_request_spec, build_task_spec
from backend.v2.models import RunStatus
from backend.v2.pipeline import build_draft_run, execute_report_run
from backend.v2.reference_data import match_reference_pack
from backend.v2.repository import FileRunRepository


GOLDEN_CASES_PATH = ROOT / "reports" / "evals" / "golden_cases.json"
RUN_ROOT = ROOT / "tmp" / "golden_runs"
SAMPLES_ROOT = ROOT / "reports" / "samples"
EVALS_ROOT = ROOT / "reports" / "evals"


def load_cases() -> list[dict[str, Any]]:
    return json.loads(GOLDEN_CASES_PATH.read_text(encoding="utf-8"))


def default_answers(prompt: str) -> dict[str, str]:
    pack = match_reference_pack(prompt)
    return {
        "decision-context": "Choose a primary platform for a production pilot in the next two quarters.",
        "dimensions": ", ".join((pack.evaluation_dimensions if pack else ["quality", "cost", "risk", "operations"])[:4]),
        "geography": "global",
        "budget": "Prefer pragmatic operating cost and privacy-aware deployment.",
    }


def reset_case_dirs(case_id: str) -> None:
    shutil.rmtree(RUN_ROOT / case_id, ignore_errors=True)
    shutil.rmtree(SAMPLES_ROOT / case_id, ignore_errors=True)
    audit_path = ROOT / "reports" / "audits" / f"{case_id}.json"
    if audit_path.exists():
        audit_path.unlink()


def has_heading(report_markdown: str, heading: str) -> bool:
    return f"## {heading}" in report_markdown or f"# {heading}" in report_markdown


async def run_case(case: dict[str, Any]) -> dict[str, Any]:
    case_id = str(case["case_id"])
    prompt = str(case["prompt"])
    reset_case_dirs(case_id)

    request_spec = build_request_spec(prompt, depth="standard")
    clarification_pack = build_clarification_pack(case_id, request_spec)
    task_spec = build_task_spec(request_spec, answers=default_answers(prompt))

    repo = FileRunRepository(root=str(RUN_ROOT), reports_root=str(SAMPLES_ROOT))
    summary = build_draft_run(case_id, prompt, depth="standard")
    summary.request_spec = request_spec
    summary.task_spec = task_spec
    summary.status = RunStatus.RUNNING
    repo.create_run(summary)

    events: list[dict[str, Any]] = []

    async def emit(event) -> None:
        events.append(event.model_dump(mode="json"))

    summary = await execute_report_run(repo, summary, task_spec, emit)

    report_dir = repo.report_dir(case_id)
    report_markdown = (report_dir / "report.md").read_text(encoding="utf-8")
    evidence_ledger = repo.load_artifact(case_id, "evidence_ledger.json") or []
    claim_table = repo.load_artifact(case_id, "claim_table.json") or []
    source_ledger = repo.load_artifact(case_id, "source_ledger.json") or []
    audit_summary = repo.load_artifact(case_id, "audit_summary.json") or {}
    quality_assessment = repo.load_artifact(case_id, "quality_assessment.json") or {}
    quality_iterations = repo.load_artifact(case_id, "quality_iterations.json") or []

    checks = [
        {
            "name": "report_type_matches",
            "passed": request_spec.report_type.value == case["expected_task_type"],
            "details": request_spec.report_type.value,
        },
        {
            "name": "clarification_fields_present",
            "passed": set(case["expected_clarification_fields"]).issubset(
                {question.field.value for question in clarification_pack.questions}
            ),
            "details": [question.field.value for question in clarification_pack.questions],
        },
        {
            "name": "must_have_sections_present",
            "passed": all(has_heading(report_markdown, heading) for heading in case["must_have_sections"]),
            "details": case["must_have_sections"],
        },
        {
            "name": "must_cover_questions_present",
            "passed": set(case["must_cover_questions"]).issubset(set(task_spec.must_cover_questions)),
            "details": task_spec.must_cover_questions,
        },
        {
            "name": "minimum_evidence_met",
            "passed": (
                len(evidence_ledger) >= case["minimum_evidence_expectations"]["min_evidence_items"]
                and len(claim_table) >= case["minimum_evidence_expectations"]["min_claims"]
                and len(source_ledger) >= case["minimum_evidence_expectations"]["min_sources"]
            ),
            "details": {
                "evidence_items": len(evidence_ledger),
                "claims": len(claim_table),
                "sources": len(source_ledger),
            },
        },
        {
            "name": "audit_released",
            "passed": audit_summary.get("release_status") == "released",
            "details": audit_summary,
        },
        {
            "name": "quality_score_floor",
            "passed": float(quality_assessment.get("overall_score", 0.0) or 0.0) >= 45.0,
            "details": quality_assessment,
        },
    ]

    case_result = {
        "case_id": case_id,
        "prompt": prompt,
        "expected_task_type": case["expected_task_type"],
        "actual_task_type": request_spec.report_type.value,
        "status": summary.status.value,
        "passed": all(check["passed"] for check in checks),
        "checks": checks,
        "quality_score": quality_assessment.get("overall_score"),
        "quality_verdict": quality_assessment.get("verdict"),
        "quality_iteration_count": len(quality_iterations),
        "report_dir": str(report_dir),
        "run_dir": str(repo.run_dir(case_id)),
        "event_count": len(events),
    }
    (report_dir / "case_result.json").write_text(
        json.dumps(case_result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return case_result


async def run_cases(selected_case_ids: set[str] | None) -> dict[str, Any]:
    all_cases = load_cases()
    cases = [case for case in all_cases if not selected_case_ids or case["case_id"] in selected_case_ids]
    results = []
    for case in cases:
        results.append(await run_case(case))

    passed = [result for result in results if result["passed"]]
    failed = [result for result in results if not result["passed"]]
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_cases": len(results),
        "passed_cases": len(passed),
        "failed_cases": len(failed),
        "results": results,
    }
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic golden evaluations for Smart Report v2.")
    parser.add_argument(
        "--case-id",
        action="append",
        default=[],
        help="Run only one or more specific golden cases",
    )
    args = parser.parse_args()

    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    SAMPLES_ROOT.mkdir(parents=True, exist_ok=True)
    EVALS_ROOT.mkdir(parents=True, exist_ok=True)

    summary = asyncio.run(run_cases(set(args.case_id) if args.case_id else None))

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    latest_path = EVALS_ROOT / "latest.json"
    snapshot_path = EVALS_ROOT / f"golden_eval_{timestamp}.json"
    latest_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    snapshot_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["failed_cases"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
