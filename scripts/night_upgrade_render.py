"""Render consulting + legacy DOCX from the final_report.json produced by the prod run.

Also renders all charts from final.charts as PNG files so the consulting renderer
can embed them.

Usage:
    python -m scripts.night_upgrade_render <run_dir>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from smart_report.models import ChartSpec, FinalReport
from smart_report.exporters.chart_renderer import render_chart


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        # Pick most recent night_upgrade/<ts> dir
        base = Path("runs/night_upgrade")
        candidates = sorted(
            [p for p in base.iterdir() if p.is_dir() and p.name.startswith("20")]
        )
        if not candidates:
            print("No run dirs found", file=sys.stderr)
            return 1
        run_dir = candidates[-1]
    else:
        run_dir = Path(argv[1])

    print(f"Run dir: {run_dir}")

    # Load the final report JSON
    fr_json = json.loads((run_dir / "final_report.json").read_text(encoding="utf-8"))
    final = FinalReport.model_validate(fr_json)
    print(
        f"Loaded FinalReport: qa={len(final.qa_section)} "
        f"tables={len(final.tables)} charts={len(final.charts)} "
        f"callouts={len(final.callouts)} key_nums={len(final.key_numbers_highlight)} "
        f"ranking={len(final.ranking)}"
    )

    # 1. Render all charts to PNG
    chart_dir = run_dir / "charts"
    chart_dir.mkdir(exist_ok=True)
    chart_paths: list[Path] = []
    for idx, spec in enumerate(final.charts):
        # docx_v4_consulting looks up by chart_{idx}.png or chart_{idx:02d}.png
        out = chart_dir / f"chart_{idx:02d}.png"
        try:
            path = render_chart(spec, out)
            chart_paths.append(path)
            print(f"  chart {idx}: {spec.chart_type} · {spec.title!r} → {out.name}")
        except Exception as e:
            print(f"  chart {idx}: FAILED ({e})")
    print(f"Rendered {len(chart_paths)}/{len(final.charts)} charts")

    # 2. Render consulting DOCX
    from smart_report.exporters.docx_v4_consulting import render_consulting_docx

    consulting_path = run_dir / "final_report_consulting.docx"
    render_consulting_docx(final, consulting_path, chart_dir=chart_dir)
    size_kb = consulting_path.stat().st_size / 1024
    print(f"Consulting DOCX: {consulting_path} ({size_kb:.1f} KB)")

    # 3. Render legacy DOCX for contrast
    try:
        from smart_report.exporters.render import write_docx as legacy_write_docx
        from smart_report.exporters.v4_to_report import v4_to_report_dict

        report = v4_to_report_dict(final)
        legacy_path = run_dir / "final_report_legacy.docx"
        legacy_write_docx(legacy_path, report)
        size_kb = legacy_path.stat().st_size / 1024
        print(f"Legacy DOCX:     {legacy_path} ({size_kb:.1f} KB)")
    except Exception as e:
        print(f"Legacy DOCX: FAILED ({e.__class__.__name__}: {e})")

    print()
    print("Done. Files in:", run_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
