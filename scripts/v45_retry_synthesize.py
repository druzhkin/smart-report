"""Retry only the synthesize step for a v4.5 session where Intake+Analyzer
already succeeded but Synthesize hit OpenRouter 402 or timed out.

Assumes the backend is running on :8010 and the session has `analysis` populated
server-side. If the backend process was restarted, the in-memory session store
is empty — recreate the session from the saved JSON artefacts first via
`recreate_session_from_artefacts()`.

Usage:
    # retry on the existing session held by a running backend:
    python -m scripts.v45_retry_synthesize <session_id>

    # if backend was restarted, point at a saved run dir; the script will
    # restore the session to the backend's store and then retry:
    python -m scripts.v45_retry_synthesize <session_id> --run-dir runs/night_upgrade/<ts>
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

API = "http://127.0.0.1:8010"


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def recreate_session_from_artefacts(client: httpx.Client, session_id: str, run_dir: Path) -> None:
    """Restore a session to the backend's V4SessionStore using saved JSON.

    This hits an internal restore endpoint; if that endpoint doesn't exist
    (most likely), we re-upload the fixture files and re-run analyze/prompt
    which defeats the purpose. Instead, print a clear hint to restart the
    backend WITHOUT killing it, or run the full pipeline again.
    """
    raise NotImplementedError(
        "Session restore not implemented — the backend needs a POST /admin/restore "
        "endpoint. For now, keep the backend running between the failed Synthesize "
        "and this retry. If the backend was restarted, you must re-run the full "
        "prod script (which will consume Intake+Analyzer credits again)."
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("session_id")
    parser.add_argument("--run-dir", type=Path, default=None)
    parser.add_argument("--timeout", type=float, default=1500.0)
    args = parser.parse_args()

    out_dir = args.run_dir or (Path("runs/v4_5") / datetime.utcnow().strftime("%Y%m%dT%H%M%SZ"))
    out_dir.mkdir(parents=True, exist_ok=True)

    # trust_env=False bypasses http_proxy trap on Windows
    client = httpx.Client(base_url=API, timeout=args.timeout, trust_env=False)

    # Step 1: probe that session exists
    log(f"Probing session {args.session_id}")
    r = client.get(f"/api/v4/sessions/{args.session_id}")
    if r.status_code == 404:
        if args.run_dir:
            log("Session not found in backend store. Attempting restore from run dir.")
            recreate_session_from_artefacts(client, args.session_id, args.run_dir)
        else:
            log(
                f"ERROR: session {args.session_id} not in backend store and no --run-dir provided. "
                "Backend was likely restarted — restart it BEFORE running this script, or pass --run-dir."
            )
            return 1
    r.raise_for_status()
    session = r.json()
    log(f"  status={session.get('status')}  total_cost_rub={session.get('total_cost_rub')}")

    if session.get("analysis") is None:
        log("ERROR: session has no analysis — cannot synthesize. Run analyze first.")
        return 2

    # Step 2: synthesize (with full retry chain: bibliography + audit + critic + language)
    log(f"Synthesize (Opus-4.7 + retry chain, up to {args.timeout/60:.0f} min budget)")
    t0 = time.time()
    r = client.post(f"/api/v4/sessions/{args.session_id}/synthesize")
    r.raise_for_status()
    final = r.json()
    dt = time.time() - t0
    log(
        f"  synthesized in {dt:.1f}s; "
        f"qa={len(final.get('qa_section', []))} "
        f"tables={len(final.get('tables', []))} "
        f"charts={len(final.get('charts', []))} "
        f"callouts={len(final.get('callouts', []))} "
        f"key_numbers={len(final.get('key_numbers_highlight', []))} "
        f"ranking={len(final.get('ranking', []))} "
        f"sources={final.get('source_count')} "
        f"citation_coverage={final.get('citation_coverage')}"
    )

    (out_dir / "final_report.json").write_text(
        json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # v4.5 metrics from metadata
    meta = final.get("metadata") or {}
    coverage = meta.get("coverage_audit")
    consistency = meta.get("consistency_check")
    language = meta.get("language_lint")
    if coverage:
        log(f"  coverage_audit: {coverage.get('verdict')}  pct={coverage.get('coverage_pct'):.2f}  facts_in_final={coverage.get('facts_in_final')}/{coverage.get('high_relevance_total')}")
    if consistency:
        sev = consistency.get("severity_summary", {})
        log(f"  consistency_check: {consistency.get('overall_verdict')}  critical={sev.get('critical', 0)}  material={sev.get('material', 0)}  minor={sev.get('minor', 0)}")
    if language:
        log(f"  language_lint: {language.get('warnings_count')} warnings")

    # Step 3: re-fetch session for final total cost
    r = client.get(f"/api/v4/sessions/{args.session_id}")
    r.raise_for_status()
    sess_after = r.json()
    (out_dir / "session_final.json").write_text(
        json.dumps(sess_after, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log(f"Final total_cost_rub (session level): {sess_after.get('total_cost_rub')}")

    log("=" * 60)
    log(f"Done. Output dir: {out_dir}")
    log(f"Next: python -m scripts.night_upgrade_render {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
