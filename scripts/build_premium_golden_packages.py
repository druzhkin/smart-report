"""Build premium golden delivery packages from saved Smart Report fixtures.

This script is intentionally fixture-first. It lets us evaluate the premium
artifact layer on real completed research runs without spending on live model
calls or mutating the legacy pipeline.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.premium_golden_eval import evaluate_package_zip  # noqa: E402
from smart_report.api.v4_endpoints import _write_premium_package  # noqa: E402
from smart_report.exporters import sanitize_final_report  # noqa: E402
from smart_report.models import (  # noqa: E402
    AnalysisOutput,
    DetectedTool,
    FinalReport,
    ResearchPrompt,
    UploadedMarkdown,
    V4Session,
)


@dataclass
class BuiltGoldenPackage:
    label: str
    fixture_json: str
    package_zip: str
    eval_json: str
    overall_score: int
    verdict: str
    blockers: list[str]


def build_from_fixture(
    *,
    fixture_json: Path,
    label: str | None,
    out_root: Path,
    visual_review_approved: bool = False,
) -> BuiltGoldenPackage:
    payload = _read_json(fixture_json)
    task_label = _safe_label(label or fixture_json.stem)
    task_dir = out_root / task_label
    task_dir.mkdir(parents=True, exist_ok=True)

    session = _session_from_fixture(payload, fallback_session_id=task_label)
    if session.final_report is None:
        raise SystemExit(f"{fixture_json} has no final_report.")
    client_report = sanitize_final_report(session.final_report)

    package_zip = _write_premium_package(
        task_dir / "premium_delivery_package.zip",
        session,
        client_report,
        visual_review_approved=visual_review_approved,
    )
    result = evaluate_package_zip(label=task_label, package_zip_path=package_zip)
    eval_json = task_dir / "golden_eval.json"
    eval_json.write_text(json.dumps(asdict(result), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return BuiltGoldenPackage(
        label=task_label,
        fixture_json=str(fixture_json),
        package_zip=str(package_zip),
        eval_json=str(eval_json),
        overall_score=result.overall_score,
        verdict=result.verdict,
        blockers=result.blockers,
    )


def build_from_manifest(
    *,
    manifest_path: Path,
    out_root: Path,
    visual_review_approved: bool = False,
) -> list[BuiltGoldenPackage]:
    payload = _read_json(manifest_path)
    tasks = payload.get("tasks") if isinstance(payload, dict) else payload
    if not isinstance(tasks, list):
        raise SystemExit("Fixture manifest must be a JSON list or an object with a 'tasks' list.")

    base_dir = manifest_path.parent
    built = []
    for idx, task in enumerate(tasks, start=1):
        if not isinstance(task, dict):
            raise SystemExit(f"Fixture manifest task #{idx} must be an object.")
        raw_fixture = task.get("fixture_json")
        if not raw_fixture:
            raise SystemExit(f"Fixture manifest task #{idx} has no fixture_json.")
        fixture_json = Path(str(raw_fixture))
        if not fixture_json.is_absolute():
            fixture_json = base_dir / fixture_json
        built.append(
            build_from_fixture(
                fixture_json=fixture_json,
                label=str(task.get("label") or fixture_json.stem),
                out_root=out_root,
                visual_review_approved=visual_review_approved,
            )
        )
    return built


def _session_from_fixture(payload: dict[str, Any], *, fallback_session_id: str) -> V4Session:
    final_report = FinalReport.model_validate(payload["final_report"])
    analysis = AnalysisOutput.model_validate(payload["analysis"]) if payload.get("analysis") else None
    research_prompt = _research_prompt_from_payload(payload.get("research_prompt"))
    source_reports = _uploaded_markdown_stubs(payload.get("uploads_meta") or [])

    session_id = str(
        payload.get("query_id")
        or final_report.session_id
        or fallback_session_id
    )
    return V4Session.model_validate(
        {
            "session_id": session_id,
            "raw_question": str(payload.get("question") or final_report.question),
            "research_prompt": research_prompt.model_dump(mode="json"),
            "source_reports": [item.model_dump(mode="json") for item in source_reports],
            "analysis": analysis.model_dump(mode="json") if analysis else None,
            "followup_reports": [],
            "final_report": final_report.model_dump(mode="json"),
            "status": "synthesized",
            "created_at": payload.get("ran_at_utc") or "2026-04-25T00:00:00+00:00",
            "total_cost_rub": float(payload.get("total_cost_rub") or 0),
        }
    )


def _research_prompt_from_payload(raw: Any) -> ResearchPrompt:
    if isinstance(raw, dict):
        return ResearchPrompt.model_validate(raw)
    return ResearchPrompt(
        full_prompt=str(raw or ""),
        reasoning="Loaded from saved fixture for premium golden evaluation.",
    )


def _uploaded_markdown_stubs(items: list[Any]) -> list[UploadedMarkdown]:
    reports: list[UploadedMarkdown] = []
    valid_tools = set(DetectedTool.__args__)  # type: ignore[attr-defined]
    for idx, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
        tool = item.get("tool")
        reports.append(
            UploadedMarkdown(
                filename=str(item.get("filename") or f"source_{idx}.md"),
                content="",
                detected_tool=tool if tool in valid_tools else None,
                word_count=0,
            )
        )
    return reports


def _read_json(path: Path) -> Any:
    if not path.exists():
        raise SystemExit(f"File does not exist: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_label(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "_", value.strip()).strip("._-")
    return slug or "golden_task"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture-json", action="append", type=Path)
    parser.add_argument("--fixture-manifest", type=Path)
    parser.add_argument("--label", help="Label for a single --fixture-json run.")
    parser.add_argument("--out-root", type=Path, default=Path("output/golden"))
    parser.add_argument("--summary-json", type=Path)
    parser.add_argument("--visual-review-approved", action="store_true")
    args = parser.parse_args()

    if not args.fixture_json and not args.fixture_manifest:
        raise SystemExit("Pass --fixture-json or --fixture-manifest.")
    if args.label and (not args.fixture_json or len(args.fixture_json) != 1 or args.fixture_manifest):
        raise SystemExit("--label can only be used with exactly one --fixture-json and no manifest.")

    built: list[BuiltGoldenPackage] = []
    if args.fixture_manifest:
        built.extend(
            build_from_manifest(
                manifest_path=args.fixture_manifest,
                out_root=args.out_root,
                visual_review_approved=args.visual_review_approved,
            )
        )
    for fixture_json in args.fixture_json or []:
        built.append(
            build_from_fixture(
                fixture_json=fixture_json,
                label=args.label,
                out_root=args.out_root,
                visual_review_approved=args.visual_review_approved,
            )
        )

    payload = {
        "built": len(built),
        "average_score": round(sum(item.overall_score for item in built) / len(built), 1) if built else 0,
        "packages": [asdict(item) for item in built],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.summary_json:
        args.summary_json.parent.mkdir(parents=True, exist_ok=True)
        args.summary_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
