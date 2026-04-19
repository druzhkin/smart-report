"""Render the 3 Synthesizer bake-off finalists into DOCX for spot-check.

Input: `runs/v45_bakeoff/<ts>/synth_reports_v2/{model}.json` — each file has
shape {"model": ..., "parsed": FinalReport, "raw_text": ...}.

Output: same dir, one `{model}.docx` per model, via docx_v4_consulting.

Usage:
    python -m scripts.render_synth_finalists [<ts>]
    # defaults to latest bake-off run dir
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from smart_report.models import FinalReport
from smart_report.exporters.docx_v4_consulting import render_consulting_docx


def main(argv: list[str]) -> int:
    base = Path("runs/v45_bakeoff")
    if len(argv) >= 2:
        run_dir = base / argv[1]
    else:
        candidates = sorted([p for p in base.iterdir() if p.is_dir() and p.name.startswith("20")])
        if not candidates:
            print("No bake-off run dirs found", file=sys.stderr)
            return 1
        run_dir = candidates[-1]

    v2_dir = run_dir / "synth_reports_v2"
    if not v2_dir.exists():
        print(f"synth_reports_v2 not found in {run_dir}", file=sys.stderr)
        return 1

    finalists = ["sonnet-4.6", "opus-4.7", "gemini-3.1-pro"]
    for slug in finalists:
        json_path = v2_dir / f"{slug}.json"
        if not json_path.exists():
            print(f"  {slug}: JSON missing, skipping")
            continue

        data = json.loads(json_path.read_text(encoding="utf-8"))
        parsed = data.get("parsed")
        if not parsed:
            print(f"  {slug}: no 'parsed' field, skipping")
            continue

        try:
            final = FinalReport.model_validate(parsed)
        except Exception as e:
            print(f"  {slug}: FinalReport validation failed — {e!r}")
            continue

        out_path = v2_dir / f"{slug}.docx"
        try:
            render_consulting_docx(final, out_path)
            size_kb = out_path.stat().st_size / 1024
            print(
                f"  {slug}: qa={len(final.qa_section)} "
                f"tables={len(final.tables)} charts={len(final.charts)} "
                f"synth_chars={len(final.main_synthesis)} "
                f"-> {out_path.name} ({size_kb:.0f} KB)"
            )
        except Exception as e:
            print(f"  {slug}: render failed — {e!r}")

    print(f"\nAll 3 finalists rendered to: {v2_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
