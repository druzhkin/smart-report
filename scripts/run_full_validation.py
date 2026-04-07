from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVALS_ROOT = ROOT / "reports" / "evals"
SAMPLES_ROOT = ROOT / "reports" / "samples"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def resolve_python() -> str:
    candidate = ROOT / "backend" / ".venv" / "Scripts" / "python.exe"
    return str(candidate if candidate.exists() else Path(sys.executable))


def resolve_node_command(name: str) -> str:
    if os.name == "nt":
        return f"{name}.cmd"
    return name


def run_step(name: str, command: list[str], cwd: Path) -> dict:
    started_at = datetime.now(timezone.utc)
    completed = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "name": name,
        "command": command,
        "cwd": str(cwd),
        "started_at": started_at.isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "returncode": completed.returncode,
        "stdout": completed.stdout[-12000:],
        "stderr": completed.stderr[-12000:],
        "passed": completed.returncode == 0,
    }


def artifact_checks() -> dict:
    from backend.v2.audit import audit_report_package

    sample_dirs = [path for path in SAMPLES_ROOT.iterdir() if path.is_dir()] if SAMPLES_ROOT.exists() else []
    audits = []
    for sample_dir in sample_dirs:
        summary = audit_report_package(sample_dir)
        audits.append(
            {
                "sample_dir": str(sample_dir),
                "release_status": summary.release_status,
                "failures": summary.failures,
                "warnings": summary.warnings,
            }
        )
    passed = all(item["release_status"] == "released" for item in audits) if audits else False
    return {
        "name": "artifact_checks",
        "passed": passed,
        "sample_count": len(audits),
        "audits": audits,
    }


def main() -> int:
    EVALS_ROOT.mkdir(parents=True, exist_ok=True)
    python = resolve_python()
    npm = resolve_node_command("npm")
    npx = resolve_node_command("npx")

    steps = [
        run_step(
            "backend_tests",
            [python, "-m", "pytest", "backend/tests/test_v2_intake.py", "backend/tests/test_v2_pipeline.py", "-q"],
            ROOT,
        ),
        run_step(
            "frontend_build",
            [npm, "run", "build"],
            ROOT / "frontend",
        ),
        run_step(
            "integration_tests",
            [python, "-m", "pytest", "backend/tests/test_v2_api.py", "-q"],
            ROOT,
        ),
        run_step(
            "frontend_e2e",
            [npx, "playwright", "test", "tests/e2e/report-flow.spec.ts"],
            ROOT / "frontend",
        ),
        run_step(
            "report_generation_smoke",
            [python, "scripts/run_golden_evals.py", "--case-id", "llm-observability"],
            ROOT,
        ),
    ]
    steps.append(artifact_checks())

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "steps": steps,
        "passed": all(step["passed"] for step in steps),
    }
    latest_path = EVALS_ROOT / "full_validation_latest.json"
    latest_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
