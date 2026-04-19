"""Final prod run for Night Upgrade v4.

Drives the full v4 pipeline on the 4 fixture markdown files:
  question → createSession → uploadReports → analyze → synthesize → FinalReport

Then renders both consulting and legacy DOCX exports for visual contrast.

Usage:
    python -m scripts.night_upgrade_prod_run
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

API = os.environ.get("NIGHT_API", "http://127.0.0.1:8010")
FIXTURES_DIR = Path("runs/night_upgrade/fixtures")
FIXTURE_FILES = [
    "deep-research-report-1.md",
    "deep-research-report-2.md",
    "amenities-main.md",
    "amenities-methodology.md",
]

QUESTION = (
    "мне нужен полный глубокий обзор по бизнес и премиум новостройкам москвы и анализ мировых практик – "
    "нужно понять, что реально пользуется спросом у покупателей а что нет, какие параметры комплекса: "
    "архитектура, фасады, мопы, финтес, бассейны, сигарные, и прочее. Какие именно параметры проекта, "
    "инфраструктуры и аменитис реально нужны и сколько покупатели готовы за это платить через рост цены. "
    "Есть ли оптимальный баланс в ассртименте аменитис, есть ли потимальный экономический баланс для "
    "застройщика по аменитис (потеря площадей, влияние на цену, окупаемоть аменитис). Нужный полный "
    "гглубокйи полноценный разбор для уровня акционера, с проверенными цифрами, надежными источниками, "
    "выводами, аналитиой синтезом и прочеим. Нужен отет а не просто обзор"
)


def log(msg: str) -> None:
    now = datetime.now().strftime("%H:%M:%S")
    print(f"[{now}] {msg}", flush=True)


def main() -> int:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(f"runs/night_upgrade/{ts}")
    out_dir.mkdir(parents=True, exist_ok=True)
    preview_dir = out_dir / "preview"
    preview_dir.mkdir(exist_ok=True)

    log(f"Output dir: {out_dir}")

    # trust_env=False bypasses system http_proxy trap on Windows
    client = httpx.Client(base_url=API, timeout=300.0, trust_env=False)

    # 1. Create session
    log("Step 1/4: createSession")
    r = client.post("/api/v4/sessions", json={"question": QUESTION})
    r.raise_for_status()
    session_id = r.json()["session_id"]
    log(f"  session_id = {session_id}")

    # 2. Generate prompt (Opus call #1)
    log("Step 2/4: generate-prompt (Opus-4.7 #1)")
    t0 = time.time()
    r = client.post(f"/api/v4/sessions/{session_id}/generate-prompt")
    r.raise_for_status()
    prompt = r.json()
    log(f"  prompt generated in {time.time()-t0:.1f}s, {len(prompt.get('full_prompt',''))} chars")
    (out_dir / "research_prompt.json").write_text(
        json.dumps(prompt, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 3. Upload reports
    log("Step 3/4: upload-reports (4 markdown files)")
    files_payload = []
    for name in FIXTURE_FILES:
        p = FIXTURES_DIR / name
        if not p.exists():
            log(f"  ERROR: fixture missing: {p}")
            return 1
        files_payload.append(
            ("files", (name, p.read_bytes(), "text/markdown"))
        )
    r = client.post(f"/api/v4/sessions/{session_id}/upload-reports", files=files_payload)
    r.raise_for_status()
    log(f"  uploaded {len(FIXTURE_FILES)} files")

    # 4. Analyze (Opus call #2)
    log("Step 4a/4: analyze (Opus-4.7 #2)")
    t0 = time.time()
    r = client.post(f"/api/v4/sessions/{session_id}/analyze")
    r.raise_for_status()
    analysis = r.json()
    log(
        f"  analyzed in {time.time()-t0:.1f}s; "
        f"consensus={len(analysis.get('consensus_claims',[]))} "
        f"conflicts={len(analysis.get('conflicts',[]))} "
        f"gaps={len(analysis.get('gaps',[]))} "
        f"followups={len(analysis.get('followup_prompts',[]))}"
    )
    (out_dir / "analysis_output.json").write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 5. Synthesize (Opus call #3 — the big one with new structured output)
    log("Step 4b/4: synthesize (Opus-4.7 #3, structured output)")
    t0 = time.time()
    r = client.post(f"/api/v4/sessions/{session_id}/synthesize")
    r.raise_for_status()
    final = r.json()
    log(
        f"  synthesized in {time.time()-t0:.1f}s; "
        f"qa={len(final.get('qa_section',[]))} "
        f"tables={len(final.get('tables',[]))} "
        f"charts={len(final.get('charts',[]))} "
        f"callouts={len(final.get('callouts',[]))} "
        f"key_numbers={len(final.get('key_numbers_highlight',[]))} "
        f"ranking={len(final.get('ranking',[]))}"
    )
    (out_dir / "final_report.json").write_text(
        json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 6. Session summary
    r = client.get(f"/api/v4/sessions/{session_id}")
    r.raise_for_status()
    session = r.json()
    total_cost = session.get("total_cost_rub", 0.0)
    log(f"Session total_cost_rub: {total_cost}  (note: _accumulate_cost may not be wired — see llm_log.jsonl for truth)")

    (out_dir / "session.json").write_text(
        json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    log("=" * 60)
    log("Prod run complete. Next: render consulting + legacy DOCX.")
    log(f"session_id: {session_id}")
    log(f"output dir: {out_dir}")

    # Stash the session_id for the docx step
    (out_dir / "session_id.txt").write_text(session_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
