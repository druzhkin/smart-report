"""Week-7 Day 4 A/B harness — config B (Valyu hybrid) vs Step 3.3 baseline.

Loads configs/ab_run2.yaml. Two modes:

    python -m scripts.ab_run2 --plan          # $0, mock-only validation
    python -m scripts.ab_run2 --live --query q3_eu_dac   # real spend, hard-capped per config

The script does NOT re-run config A. We compare the live config-B
output against the saved Step 3.3 fixtures (same code path as today's
main, same prompts, same models for the baseline). The whole point is
to measure orchestrator delta, not LLM noise on the baseline side.

Outputs:
    runs/ab_run2/<query_id>_<config>_<utc>.json    — full V4Session payload
    runs/ab_run2/<query_id>_<config>_<utc>.summary.md  — human-readable diff
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

import yaml

if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).parent.parent
load_dotenv(dotenv_path=REPO_ROOT / ".env")

from smart_report.domain_detector import detect_query_domain
from smart_report.models import ResearchPrompt, UploadedMarkdown, V4Session
from smart_report.sources.orchestrator import SearchOrchestrator, SearchOutcome
from smart_report.sources.valyu import ValyuClient, ValyuResult
from smart_report import v4_orchestrator as v4_module
from smart_report.v4_orchestrator import V4Orchestrator, V4SessionStore

USD_RUB_RATE = 75.4
CONFIG_PATH = REPO_ROOT / "configs/ab_run2.yaml"
OUT_DIR = REPO_ROOT / "runs/ab_run2"


# ---------------------------------------------------------------------------
# Adapters
# ---------------------------------------------------------------------------


def valyu_results_to_markdown(query: str, results: list[ValyuResult]) -> str:
    """Adapt Valyu hits into a single Markdown block the v4 intake can consume.

    Format mirrors what a Perplexity DR report looks like — Sources
    section at the bottom, citation numbers in the body — so the v4
    intake's existing extraction rules work without changes.
    """
    lines = [f"# Valyu DeepSearch results — {query}", ""]
    for i, r in enumerate(results, 1):
        title = r.title or "(untitled)"
        lines.append(f"## [{i}] {title}")
        if r.publication_date:
            lines.append(f"_Published: {r.publication_date}_")
        if r.source:
            lines.append(f"_Source: {r.source}_")
        lines.append("")
        body = r.content.strip() if r.content else "(no content snippet)"
        lines.append(body)
        lines.append("")
        lines.append(f"Citation: {r.url}")
        lines.append("")
    lines.append("## Sources")
    lines.append("")
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r.url}")
    return "\n".join(lines)


def _load_config() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def _load_baseline_fixture(path: str) -> dict:
    p = REPO_ROOT / path
    if not p.exists():
        raise FileNotFoundError(f"baseline fixture missing: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Plan-only path ($0): inspect what the live run would do
# ---------------------------------------------------------------------------


def plan(query_id: str | None = None) -> int:
    cfg = _load_config()
    print(f"=== ab_run2 plan ({CONFIG_PATH.name}) ===")
    queries = cfg["queries"]
    target_ids = [query_id] if query_id else list(queries.keys())
    for qid in target_ids:
        if qid not in queries:
            print(f"[plan] ERROR: query_id {qid!r} not in config")
            return 2
        q = queries[qid]
        domain = detect_query_domain(q["question"])
        expected = q.get("expected_domain")
        match = "OK" if expected and domain.value == expected else f"!= expected ({expected})"
        print(f"\n[plan] {qid}")
        print(f"  question: {q['question'][:120]}")
        print(f"  detected_domain: {domain.value}  ({match})")
        print(f"  baseline_fixture: {q['baseline_fixture']}")
        baseline_path = REPO_ROOT / q["baseline_fixture"]
        if baseline_path.exists():
            try:
                d = json.loads(baseline_path.read_text(encoding="utf-8"))
                ev = d.get("evaluation", {}) or {}
                print(f"  baseline cost_usd: {ev.get('cost_usd')}")
                print(f"  baseline source_count: {ev.get('source_count_in_final')}")
                print(f"  baseline grade dist: {ev.get('evidence_grade_distribution')}")
            except Exception as e:
                print(f"  baseline read FAILED: {e}")
        else:
            print(f"  baseline MISSING")

    dry = cfg["dry_run"]
    print(f"\n[plan] dry_run target: {dry['query_id']} × config {dry['config']} (cap=${dry['hard_cap_usd']})")
    print(f"[plan] stop_conditions:")
    for s in cfg["stop_conditions"]:
        print(f"   - {s}")
    print("\n[plan] OK — no spend, no LLM/Valyu calls made.")
    return 0


# ---------------------------------------------------------------------------
# Live path: run config B against one query
# ---------------------------------------------------------------------------


async def _build_config_b_uploads(question: str, max_results: int) -> tuple[list[UploadedMarkdown], SearchOutcome]:
    """Call SearchOrchestrator → Valyu → markdown → UploadedMarkdown wrapper.

    Returns ([upload], outcome). For PERPLEXITY_MANUAL primary the
    upload list is empty (caller should skip live config B for that
    query — we handle the policy decision in the caller, not here).
    """
    api_key = os.environ.get("VALYU_API_KEY")
    if not api_key:
        raise RuntimeError("VALYU_API_KEY missing — set in .env before running --live")
    valyu = ValyuClient(api_key=api_key)
    orch = SearchOrchestrator(valyu_client=valyu, max_results=max_results)
    outcome = await orch.search(question)
    if outcome.handoff_required:
        return ([], outcome)
    if not outcome.results:
        return ([], outcome)
    md = valyu_results_to_markdown(question, outcome.results)
    upload = UploadedMarkdown(
        filename=f"valyu_{outcome.domain.value}.md",
        content=md,
        detected_tool="other",
        word_count=len(md.split()),
    )
    return ([upload], outcome)


async def _run_config_b_cycle(
    question: str,
    uploads: list[UploadedMarkdown],
    models: dict[str, str],
) -> V4Session:
    store = V4SessionStore()

    class _Emitter:
        def emit(self, phase, message, *, data=None):
            print(f"  [{phase}] {message}")

    orch = V4Orchestrator(store, mock=False, emitter=_Emitter())
    sid = uuid.uuid4().hex[:12]
    store.create(session_id=sid, raw_question=question)

    sess = store.get(sid)
    sess.research_prompt = ResearchPrompt(
        full_prompt=f"[stub PM skipped for ab_run2 dry-run] Original question: {question}",
        reasoning="stub",
        expected_structure=[],
        key_entities=[],
        tips_for_search="",
    )
    sess.status = "prompt_ready"
    sess.source_reports = uploads
    sess.status = "reports_uploaded"
    store.update(sess)

    with patch.object(v4_module, "models_for_preference", lambda pref: models):
        await orch.analyze(sid)
        await orch.synthesize(sid)

    return store.get(sid)


def _save_run(query_id: str, config: str, session: V4Session, outcome: SearchOutcome | None) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = OUT_DIR / f"{query_id}_{config}_{ts}.json"
    payload = {
        "query_id": query_id,
        "config": config,
        "ran_at_utc": datetime.now(timezone.utc).isoformat(),
        "raw_question": session.raw_question,
        "valyu_outcome": {
            "backend": outcome.backend.value if outcome else None,
            "domain": outcome.domain.value if outcome else None,
            "result_count": len(outcome.results) if outcome else 0,
            "fallback_used": outcome.fallback_used if outcome else False,
            "primary_error": outcome.primary_error if outcome else None,
            "valyu_per_call_prices": [r.price for r in outcome.results] if outcome else [],
        },
        "analysis": session.analysis.model_dump() if session.analysis else None,
        "final_report": session.final_report.model_dump() if session.final_report else None,
        "total_cost_rub": session.total_cost_rub,
        "total_cost_usd_at_75_4": round(session.total_cost_rub / USD_RUB_RATE, 4),
    }
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return out_path


def _make_summary(query_id: str, config: str, session: V4Session, outcome: SearchOutcome | None, baseline: dict, out_json: Path) -> Path:
    summary_path = out_json.with_suffix(".summary.md")
    final = session.final_report
    cost_usd = session.total_cost_rub / USD_RUB_RATE
    grade_dist = {}
    if final:
        from smart_report.evidence_grades import evidence_grade_distribution
        grade_dist = evidence_grade_distribution(final)
    base_eval = baseline.get("evaluation", {}) or {}

    lines = [
        f"# A/B run 2 dry-run summary — {query_id} × config {config}",
        "",
        f"Ran at: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Cost",
        f"- Config B (live, hybrid): ${cost_usd:.4f}",
        f"- Baseline Step 3.3 (saved): ${base_eval.get('cost_usd')}",
        "",
        "## Valyu outcome",
    ]
    if outcome:
        lines.append(f"- backend: {outcome.backend.value}")
        lines.append(f"- domain: {outcome.domain.value}")
        lines.append(f"- result_count: {len(outcome.results)}")
        lines.append(f"- fallback_used: {outcome.fallback_used}")
        if outcome.primary_error:
            lines.append(f"- primary_error: {outcome.primary_error}")
        valyu_cost = sum(r.price for r in outcome.results)
        lines.append(f"- valyu_call_total: ${valyu_cost:.4f}")
    lines += [
        "",
        "## Evidence-grade distribution",
        f"- Config B: {grade_dist}",
        f"- Baseline: {base_eval.get('evidence_grade_distribution')}",
        "",
        "## Source counts",
        f"- Config B: {len(final.all_sources) if final else 0}",
        f"- Baseline: {base_eval.get('source_count_in_final')}",
        "",
        "## Stop-condition checks",
    ]
    cap = 1.50
    cost_ok = cost_usd <= cap
    valyu_ok = outcome is None or outcome.handoff_required or len(outcome.results) >= 3
    lines.append(f"- cost ≤ ${cap}: {'OK' if cost_ok else 'BREACH'} (${cost_usd:.4f})")
    lines.append(f"- Valyu hits ≥ 3: {'OK' if valyu_ok else 'BREACH'}")
    summary_path.write_text("\n".join(lines), encoding="utf-8")
    return summary_path


async def live(query_id: str) -> int:
    cfg = _load_config()
    if query_id not in cfg["queries"]:
        print(f"[live] ERROR: query_id {query_id!r} not in config")
        return 2

    q = cfg["queries"][query_id]
    config_b = cfg["configs"]["B"]
    cap = cfg["dry_run"]["hard_cap_usd"]

    print(f"=== ab_run2 LIVE — {query_id} × config B (cap ${cap}) ===")
    print(f"[live] question: {q['question']}")

    domain = detect_query_domain(q["question"])
    print(f"[live] detected domain: {domain.value}")

    print(f"[live] step 1/3 — SearchOrchestrator")
    uploads, outcome = await _build_config_b_uploads(
        q["question"], max_results=config_b["valyu_max_results"]
    )
    print(f"[live]   backend={outcome.backend.value}, results={len(outcome.results)}, fallback={outcome.fallback_used}")
    if outcome.primary_error:
        print(f"[live]   primary_error: {outcome.primary_error}")

    if outcome.handoff_required and not uploads:
        print(f"[live] STOP — query routes to PERPLEXITY_MANUAL with no Valyu fallback. ")
        print(f"[live]   Config B has no Valyu input to evaluate; baseline-only re-run is out of scope here.")
        print(f"[live]   This is the documented behaviour for RU_* queries.")
        return 0

    if outcome.results and len(outcome.results) < 3:
        print(f"[live] STOP — Valyu returned only {len(outcome.results)} hits (< 3 stop condition).")
        print(f"[live]   Logging in BLOCKERS.md and skipping analyze/synthesize to save spend.")
        return 0

    print(f"[live] step 2/3 — analyze + synthesize on {len(uploads)} uploads, models={config_b['models']}")
    session = await _run_config_b_cycle(q["question"], uploads, config_b["models"])
    cost_usd = session.total_cost_rub / USD_RUB_RATE
    print(f"[live]   cost so far: ${cost_usd:.4f}")
    if cost_usd > cap:
        print(f"[live] WARNING — cost ${cost_usd:.4f} exceeded cap ${cap}. Run completed but flag in dry_run report.")

    print(f"[live] step 3/3 — saving outputs")
    baseline = _load_baseline_fixture(q["baseline_fixture"])
    out_json = _save_run(query_id, "B", session, outcome)
    out_md = _make_summary(query_id, "B", session, outcome, baseline, out_json)
    print(f"[live]   {out_json}")
    print(f"[live]   {out_md}")
    print(f"[live] DONE. Total: ${cost_usd:.4f}")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description="ab_run2 — Day 4/5 hybrid A/B harness")
    ap.add_argument("--plan", action="store_true", help="$0 plan-only validation")
    ap.add_argument("--live", action="store_true", help="real run with cost spend")
    ap.add_argument("--query", default=None, help="query_id (default: dry_run target)")
    args = ap.parse_args()

    if args.plan == args.live:
        ap.error("specify exactly one of --plan or --live")
    if args.plan:
        return plan(args.query)
    cfg = _load_config()
    qid = args.query or cfg["dry_run"]["query_id"]
    return asyncio.run(live(qid))


if __name__ == "__main__":
    raise SystemExit(main())
