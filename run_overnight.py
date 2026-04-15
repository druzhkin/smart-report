"""Night job runner.

For each of the three queries from the brief:
  1. eval_loop(query, max_iterations=2) — produces best Report
  2. Save reports/{YYYYMMDD}-{slug}.json / .md / .docx / .pptx
  3. Log eval result (eval_loop already does this)

Runs sequentially (AWstore credit ceiling).
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

from evaluator import eval_loop
from export import to_markdown, to_json
from export_docx import export_mckinsey_docx
from export_pptx import export_pptx
from infographics import render_all

REPORTS_DIR = Path(__file__).parent / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

QUERIES: list[tuple[str, str]] = [
    (
        "world-trends-housing",
        "Какие мировые тренды 2025–2030 повлияют на жилое строительство в России — технологические, демографические, экономические, культурные, экологические",
    ),
    (
        "analytical-engine",
        "Как сделать сильный глубокий аналитический движок — методологии мышления, архитектура AI-систем, когнитивная наука, поиск и источники",
    ),
    (
        "premium-buyer-values",
        "За что реально готовы платить покупатели квартир бизнес и премиум класса в Москве и мире — конкретные ценности, исследования, фокус-группы, статистика продаж, что работает и что маркетинговый пузырь",
    ),
]


def _slugify(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE).strip().lower()
    text = re.sub(r"[\s_]+", "-", text)
    return text[:60] or "report"


async def _run_one(slug: str, query: str) -> dict:
    start = time.time()
    stamp = datetime.now().strftime("%Y%m%d")
    stem = f"{stamp}-{slug}"
    result: dict = {"slug": slug, "query": query, "stem": stem, "status": "unknown"}
    try:
        report, eval_entry = await eval_loop(query, max_iterations=2)
    except Exception as err:
        tb = traceback.format_exc()
        print(f"[runner] eval_loop FAILED for {slug}: {err}\n{tb}")
        result["status"] = f"eval_loop_failed: {err}"
        return result

    result["eval_total"] = eval_entry.get("final_total")
    result["eval_scores"] = eval_entry.get("final_scores")

    # Save artifacts
    try:
        json_path = REPORTS_DIR / f"{stem}.json"
        json_path.write_text(to_json(report), encoding="utf-8")
        result["json"] = str(json_path)

        md_path = REPORTS_DIR / f"{stem}.md"
        md_path.write_text(to_markdown(report), encoding="utf-8")
        result["md"] = str(md_path)

        images = render_all(report, stem=stem)
        result["images"] = {k: str(v) for k, v in images.items()}

        docx_path = REPORTS_DIR / f"{stem}.docx"
        export_mckinsey_docx(report, docx_path, images)
        result["docx"] = str(docx_path)

        pptx_path = REPORTS_DIR / f"{stem}.pptx"
        export_pptx(report, pptx_path, images)
        result["pptx"] = str(pptx_path)

        result["status"] = "ok"
    except Exception as err:
        tb = traceback.format_exc()
        print(f"[runner] export FAILED for {slug}: {err}\n{tb}")
        result["status"] = f"export_failed: {err}"

    result["elapsed_sec"] = round(time.time() - start, 1)
    return result


async def main() -> int:
    all_results: list[dict] = []
    for slug, query in QUERIES:
        print(f"\n{'='*80}\n[runner] START {slug}: {query}\n{'='*80}")
        res = await _run_one(slug, query)
        all_results.append(res)
        # incremental save
        summary_path = REPORTS_DIR / "overnight_summary.json"
        summary_path.write_text(
            json.dumps(all_results, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"[runner] DONE {slug}: status={res['status']} elapsed={res.get('elapsed_sec')}s")

    print("\n\n=== ИТОГО ===")
    for r in all_results:
        print(f"  {r['slug']}: {r['status']}  total={r.get('eval_total')}  time={r.get('elapsed_sec')}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
