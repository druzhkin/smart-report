"""Run 2 baseline harness — fresh Sonnet runs on current `origin/v4.5`.

Per the SESSION TASK brief: replay the Phase 3 winner-config (Sonnet 4.6
across all stages) on Q1/Q2/Q3 to get DOCX + audit + trace + cost
artefacts that a human will read with eyes. NOT reusing the
2026-04-25 comparison checkpoints — Step 3.3 synthesizer changes
landed after those checkpoints were saved, so a checkpoint reuse
would test a hybrid, not current origin/v4.5.

Usage:
    python -m scripts.run2_baseline --query q3_eu_dac
    python -m scripts.run2_baseline --query all     # fires Q1, Q2, Q3 in order

Outputs per query under docs/run2_baseline/<qid>/:
    report.docx          — rendered final report
    audit_summary.json   — release_status, evidence_quality, grades, sources
    trace.jsonl          — one event per line from the V4 cycle emitter
    cost.txt             — single line "$X.XXXX" actual spend

Path note: brief specifies runs/run2_baseline/ but our runs/ is in
.gitignore (raw LLM outputs aren't kept in git). Using docs/ instead
keeps the artefacts in origin/v4.5 per acceptance §6 without
touching .gitignore.

Per the brief: per-run hard cap $4. If a run exceeds, harness STOPS
and emits a clear message; do not auto-continue.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).parent.parent
load_dotenv(dotenv_path=REPO_ROOT / ".env")

from smart_report.exporters import render_docx
from smart_report.evidence_grades import evidence_grade_distribution
from smart_report.models import ResearchPrompt, UploadedMarkdown, V4Session
from smart_report import v4_orchestrator as v4_module
from smart_report.v4_orchestrator import V4Orchestrator, V4SessionStore

# Self-contained query specs + helpers — INTENTIONALLY NOT importing
# from scripts.live_acceptance_run because that module monkey-patches
# httpx.Response.raise_for_status globally (line ~48), which interacts
# poorly with smart_report.llm's retry shim. The monkey-patch is the
# leading hypothesis for the Sonnet hang debugged in Block A of the
# 2026-04-26 unblock session — see daily/sonnet_unblock_protocol.md.

USD_RUB_RATE = 75.4
SONNET = "anthropic/claude-sonnet-4.6"
DOWNLOADS = Path("C:/Users/rodina-adm/Downloads")

COMPARISON_QUERIES = [
    {
        "id": "q1_ev",
        "question": (
            "Сравните перспективы трёх лидеров электромобильного рынка в "
            "России (Москвич, АВТОВАЗ, Evolute) на горизонте 3 лет в условиях "
            "конкуренции с китайскими брендами BYD, Geely, Chery"
        ),
        "uploads": [
            (
                "Перспективы-российских-производителей-электромобилей-в-условиях-китайской-конкуренции-прогноз-на-2026–2029-годы.md",
                "openai_dr",
            ),
            (
                "«Сравните перспективы трёх лидеров электромобильно.md",
                "perplexity",
            ),
        ],
    },
    {
        "id": "q2_moscow_re",
        "question": (
            "Какие тренды повлияют на девелоперов бизнес-сегмента жилья в "
            "Москве в 2026-2027?"
        ),
        "uploads": [
            (
                "Тренды,-влияющие-на-московских-девелоперов-жилого-сегмента-в-2026-2027-годах.md",
                "openai_dr",
            ),
            (
                "«Какие тренды повлияют на девелоперов бизнес-сегме.md",
                "perplexity",
            ),
        ],
    },
    {
        "id": "q3_eu_dac",
        "question": (
            "How is Direct Air Capture regulated in the EU and what subsidies "
            "are available in 2026?"
        ),
        "uploads": [
            (
                "EU-Direct-Air-Capture-Regulation-and-2026-Subsidies-Comprehensive-Framework-and-Funding-Landscape.md",
                "openai_dr",
            ),
        ],
    },
]


def _detect_tool(filename: str) -> str:
    name = filename.lower()
    if "perplexity" in name or "pplx" in name:
        return "perplexity"
    if "openai" in name or "chatgpt" in name or "deep-research" in name:
        return "openai_dr"
    if "claude" in name:
        return "claude"
    return "other"


def _load_markdown_uploads(specs: list[tuple[str, str]]) -> list[UploadedMarkdown]:
    uploads: list[UploadedMarkdown] = []
    for filename, tool in specs:
        p = DOWNLOADS / filename
        text = p.read_text(encoding="utf-8")
        uploads.append(
            UploadedMarkdown(
                filename=filename,
                content=text,
                detected_tool=tool,
                word_count=len(text.split()),
            )
        )
    return uploads

OUT_ROOT = REPO_ROOT / "docs/run2_baseline"
PER_RUN_HARD_CAP_USD = 4.00


def _all_stages_sonnet() -> dict[str, str]:
    return {
        "prompt_master": SONNET,
        "analyzer": SONNET,
        "synthesizer": SONNET,
        "critic": SONNET,
    }


def _derive_release_status(session: V4Session, exception_during_run: bool) -> str:
    """Map session state into release_status per the SESSION TASK brief.

    Definitions:
      pass     — final_report exists, evidence_quality is OK, no exception
      degraded — final_report exists, evidence_quality is LOW or coverage
                 retry fired (Track 3 / data_audit critical_failure)
      blocked  — final_report missing or unrecoverable exception
    """
    if exception_during_run or session.final_report is None:
        return "blocked"
    eq = session.final_report.metadata.get("evidence_quality")
    if eq and eq != "OK":
        return "degraded"
    return "pass"


async def _run_one_query(qid: str, spec: dict, out_dir: Path) -> tuple[str, float]:
    """Run a single query end-to-end and persist all artefacts.

    Returns (release_status, cost_usd).
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*70}")
    print(f"  Run 2 baseline — {qid}")
    print(f"  question: {spec['question'][:120]}")
    print(f"  uploads: {len(spec['uploads'])} markdown(s)")
    print(f"  output:  {out_dir}")
    print(f"{'='*70}\n")

    uploads = _load_markdown_uploads(spec["uploads"])
    total_input_words = sum(u.word_count for u in uploads)
    print(f"  input words total: {total_input_words:,}")

    captured_events: list[dict] = []

    class _Emitter:
        def emit(self, phase, message, *, data=None):
            captured_events.append({
                "ts": datetime.now(timezone.utc).isoformat(),
                "phase": phase,
                "message": message,
                "data": data,
            })
            print(f"  [{phase}] {message}")

    store = V4SessionStore()
    orch = V4Orchestrator(store, mock=False, emitter=_Emitter())
    sid = uuid.uuid4().hex[:12]
    store.create(session_id=sid, raw_question=spec["question"])

    sess = store.get(sid)
    sess.source_reports = uploads
    sess.status = "reports_uploaded"
    store.update(sess)

    stages = _all_stages_sonnet()
    print(f"  models: {stages}")

    exception_during_run = False
    try:
        with patch.object(v4_module, "models_for_preference", lambda pref: stages):
            await orch.generate_prompt(sid)
            await orch.analyze(sid)
            await orch.synthesize(sid)
    except Exception as e:
        exception_during_run = True
        captured_events.append({
            "ts": datetime.now(timezone.utc).isoformat(),
            "phase": "exception",
            "message": f"{type(e).__name__}: {e}",
            "data": None,
        })
        print(f"  [exception] {type(e).__name__}: {e}")

    session = store.get(sid)
    cost_usd = session.total_cost_rub / USD_RUB_RATE
    final = session.final_report
    release_status = _derive_release_status(session, exception_during_run)

    # Render DOCX (only if synth succeeded)
    docx_path = out_dir / "report.docx"
    if final is not None:
        try:
            render_docx(final, docx_path)
            print(f"  [docx] rendered: {docx_path}  ({docx_path.stat().st_size} bytes)")
        except Exception as e:
            print(f"  [docx] FAILED: {type(e).__name__}: {e}")
            release_status = "blocked"
    else:
        print(f"  [docx] SKIPPED — no final_report (status={release_status})")

    # Audit summary
    audit = {
        "query_id": qid,
        "question": spec["question"],
        "ran_at_utc": datetime.now(timezone.utc).isoformat(),
        "model_config": stages,
        "release_status": release_status,
        "exception_during_run": exception_during_run,
        "cost_usd": round(cost_usd, 4),
        "cost_rub": round(session.total_cost_rub, 2),
        "uploads": [{"filename": fn, "tool": tool} for fn, tool in spec["uploads"]],
        "uploads_total_words": total_input_words,
        "research_prompt": session.research_prompt.model_dump() if session.research_prompt else None,
        "decomposition_method": (
            getattr(session.research_prompt, "decomposition_method", "")
            if session.research_prompt
            else ""
        ),
        "sub_questions_count": (
            len(getattr(session.research_prompt, "sub_questions", []) or [])
            if session.research_prompt
            else 0
        ),
        "evidence_quality": final.metadata.get("evidence_quality") if final else None,
        "evidence_warning": final.metadata.get("evidence_warning") if final else None,
        "query_domain_detected": final.metadata.get("query_domain") if final else None,
        "gap_count_by_severity": final.metadata.get("gap_count_by_severity") if final else None,
        "source_count_in_final": len(final.all_sources) if final else 0,
        "evidence_grade_distribution": evidence_grade_distribution(final) if final else None,
        "main_synthesis_chars": len(final.main_synthesis) if final else 0,
    }
    (out_dir / "audit_summary.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )

    # Trace
    with open(out_dir / "trace.jsonl", "w", encoding="utf-8") as f:
        for ev in captured_events:
            f.write(json.dumps(ev, ensure_ascii=False, default=str) + "\n")

    # Cost
    (out_dir / "cost.txt").write_text(f"${cost_usd:.4f}\n", encoding="utf-8")

    print(f"\n  → release_status: {release_status}")
    print(f"  → cost: ${cost_usd:.4f}")
    print(f"  → grades: {audit['evidence_grade_distribution']}")
    print(f"  → sources: {audit['source_count_in_final']}")

    return (release_status, cost_usd)


async def run_all(query_ids: list[str]) -> int:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)

    spec_by_id = {q["id"]: q for q in COMPARISON_QUERIES}
    cumulative = 0.0

    for qid in query_ids:
        if qid not in spec_by_id:
            print(f"ERROR: unknown query_id {qid!r}. Known: {list(spec_by_id.keys())}")
            return 2
        spec = spec_by_id[qid]
        out_dir = OUT_ROOT / qid

        # Per-run pre-flight cost line (echoed; user is expected to mirror in BUDGET.md)
        print(f"\n>>> BUDGET pre-flight: {datetime.now(timezone.utc).strftime('%Y-%m-%d')} run2_baseline:{qid} expected≈$2.69 cap=${PER_RUN_HARD_CAP_USD}")

        status, cost = await _run_one_query(qid, spec, out_dir)
        cumulative += cost

        if cost > PER_RUN_HARD_CAP_USD:
            print(f"\n*** STOP: {qid} cost ${cost:.4f} > per-run cap ${PER_RUN_HARD_CAP_USD}.")
            print(f"    Cumulative ${cumulative:.4f}. Halting before next query.")
            return 1

        print(f"\n>>> cumulative spend so far: ${cumulative:.4f}")

    print(f"\n{'='*70}")
    print(f"DONE — {len(query_ids)} queries, total spend ${cumulative:.4f}")
    print(f"{'='*70}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--query",
        required=True,
        help="query_id (q1_ev | q2_moscow_re | q3_eu_dac) or 'all' for all three in order Q3→Q1→Q2",
    )
    args = ap.parse_args()

    if args.query == "all":
        # Per SESSION TASK §9 priority — Q3 first (where day 5 finding lives)
        query_ids = ["q3_eu_dac", "q1_ev", "q2_moscow_re"]
    else:
        query_ids = [args.query]

    return asyncio.run(run_all(query_ids))


if __name__ == "__main__":
    raise SystemExit(main())
