from __future__ import annotations

import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_report() -> dict:
    path = ROOT / "outputs" / "audit" / "latest.json"
    if not path.exists():
        return {"ok": False, "error": f"missing report: {path}"}
    return json.loads(path.read_text(encoding="utf-8"))


def _step_line(step: dict) -> str:
    icon = "PASS" if step.get("ok") else "FAIL"
    name = step.get("name", "unknown")
    sec = step.get("elapsed_sec", 0)
    code = step.get("returncode", 1)
    cmd = step.get("command", "")
    return f"- [{icon}] `{name}` ({sec}s, rc={code})\n  cmd: `{cmd}`"


def main() -> int:
    report = _load_report()
    lines: list[str] = ["## Autonomous Audit Summary"]

    if report.get("error"):
        lines.append(f"- [FAIL] {report['error']}")
    else:
        ok = bool(report.get("ok"))
        lines.append(f"- Overall: **{'PASS' if ok else 'FAIL'}**")
        lines.append(f"- Steps total: {report.get('steps_total', 0)}")
        lines.append(f"- Steps failed: {report.get('steps_failed', 0)}")
        lines.append("")
        lines.append("### Steps")
        for step in report.get("steps", []):
            lines.append(_step_line(step))

    out_dir = ROOT / "outputs" / "audit"
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / "summary.md"
    summary = "\n".join(lines).strip() + "\n"
    summary_path.write_text(summary, encoding="utf-8")

    github_step_summary = os.getenv("GITHUB_STEP_SUMMARY", "").strip()
    if github_step_summary:
        Path(github_step_summary).write_text(summary, encoding="utf-8")

    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

