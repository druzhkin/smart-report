from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from shutil import which


ROOT = Path(__file__).resolve().parents[1]


def _resolve_executable(cmd: str) -> str:
    if os.name == "nt" and cmd == "npm":
        npm_cmd = which("npm.cmd")
        if npm_cmd:
            return npm_cmd
    return cmd


@dataclass
class StepResult:
    name: str
    ok: bool
    command: str
    workdir: str
    elapsed_sec: float
    returncode: int


def _run_step(name: str, command: list[str], workdir: Path) -> StepResult:
    started = time.perf_counter()
    normalized = command.copy()
    if normalized:
        normalized[0] = _resolve_executable(normalized[0])
    process = subprocess.run(normalized, cwd=workdir, check=False)
    elapsed = time.perf_counter() - started
    return StepResult(
        name=name,
        ok=process.returncode == 0,
        command=" ".join(normalized),
        workdir=str(workdir),
        elapsed_sec=round(elapsed, 2),
        returncode=process.returncode,
    )


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name, "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}


def main() -> int:
    steps: list[StepResult] = []

    steps.append(
        _run_step(
            "backend.unit_tests",
            ["python", "-m", "pytest", "backend/tests", "-q"],
            ROOT,
        )
    )
    steps.append(
        _run_step(
            "frontend.build",
            ["npm", "run", "build"],
            ROOT / "frontend",
        )
    )
    steps.append(
        _run_step(
            "frontend.e2e",
            ["npm", "run", "test:e2e"],
            ROOT / "frontend",
        )
    )

    if _bool_env("FULL_AUDIT_RUN_INTEGRATION", default=False):
        env = os.environ.copy()
        env["RUN_INTEGRATION_TESTS"] = "1"
        started = time.perf_counter()
        proc = subprocess.run(
            ["python", "-m", "pytest", "backend/tests/test_pipeline_e2e.py", "-v"],
            cwd=ROOT,
            env=env,
            check=False,
        )
        steps.append(
            StepResult(
                name="backend.integration_e2e",
                ok=proc.returncode == 0,
                command="python -m pytest backend/tests/test_pipeline_e2e.py -v",
                workdir=str(ROOT),
                elapsed_sec=round(time.perf_counter() - started, 2),
                returncode=proc.returncode,
            )
        )

    if os.getenv("SMOKE_API_BASE", "").strip():
        steps.append(
            _run_step(
                "production.smoke",
                ["python", "scripts/prod_smoke.py"],
                ROOT,
            )
        )

    report = {
        "ok": all(step.ok for step in steps),
        "steps_total": len(steps),
        "steps_failed": len([step for step in steps if not step.ok]),
        "steps": [asdict(step) for step in steps],
    }

    audit_dir = ROOT / "outputs" / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    report_path = audit_dir / "latest.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\nAudit report saved: {report_path}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
