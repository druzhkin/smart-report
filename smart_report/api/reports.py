"""Per-user report submission for the SaaS dashboard.

Self-serve flow:
  POST /api/reports {question, uploads_text?[]}
        → creates report_id, kicks off v4 cycle in background, returns
          {report_id, status: "queued"}.
  GET  /api/reports
        → list user's reports (most recent first) with status + cost.
  GET  /api/reports/{id}
        → status + final report JSON when ready.
  GET  /api/reports/{id}/docx
        → DOCX file download.

Storage: per-user dir under data/reports/<email-slug>/<report_id>/
containing report.docx + audit_summary.json + status.json (lifecycle:
queued | running | done | error).

This goes through the same v4 orchestrator the run2_baseline harness
uses, so the SaaS path benefits from every Phase 1-3 improvement
(calibration, source-quality, gap detector). Sonnet 4.6 across stages.
Per A14: a typical report wall time is 25-45 min; the dashboard polls.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from unittest.mock import patch

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .auth import require_user
from ..exporters import render_docx
from ..evidence_grades import evidence_grade_distribution
from ..models import UploadedMarkdown
from .. import v4_orchestrator as v4_module
from ..v4_orchestrator import V4Orchestrator, V4SessionStore

log = logging.getLogger("smart_report.api.reports")

router = APIRouter(prefix="/api/v4/reports", tags=["reports"])

_REPORTS_ROOT = Path(__file__).resolve().parent.parent.parent / "data" / "reports"
_REPORTS_LOCK = threading.Lock()

USD_RUB_RATE = 75.4
SONNET = "anthropic/claude-sonnet-4.6"

_MAX_QUESTION_LEN = 2000
_MAX_UPLOAD_LEN = 200_000  # 200KB per upload
_MAX_UPLOADS = 5


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class _UploadIn(BaseModel):
    filename: str = Field(..., max_length=200)
    content: str = Field(..., max_length=_MAX_UPLOAD_LEN)


class ReportIn(BaseModel):
    question: str = Field(..., min_length=8, max_length=_MAX_QUESTION_LEN)
    uploads: list[_UploadIn] = Field(default_factory=list, max_length=_MAX_UPLOADS)


class ReportOut(BaseModel):
    id: str
    status: str
    question: str
    created_at: str
    finished_at: Optional[str] = None
    cost_usd: Optional[float] = None
    error: Optional[str] = None
    grades: Optional[dict] = None
    source_count: Optional[int] = None
    evidence_quality: Optional[str] = None


# ---------------------------------------------------------------------------
# Storage helpers
# ---------------------------------------------------------------------------


def _email_slug(email: str) -> str:
    return re.sub(r"[^a-z0-9._-]+", "_", email.lower())[:80]


def _user_dir(email: str) -> Path:
    return _REPORTS_ROOT / _email_slug(email)


def _report_dir(email: str, report_id: str) -> Path:
    return _user_dir(email) / report_id


def _read_status(email: str, report_id: str) -> dict:
    p = _report_dir(email, report_id) / "status.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_status(email: str, report_id: str, **fields) -> None:
    d = _report_dir(email, report_id)
    d.mkdir(parents=True, exist_ok=True)
    p = d / "status.json"
    cur = _read_status(email, report_id)
    cur.update(fields)
    p.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Background v4 cycle
# ---------------------------------------------------------------------------


async def _run_report_async(email: str, report_id: str, payload: ReportIn) -> None:
    """Drive the v4 cycle for this report. Persists status + DOCX + audit."""
    rdir = _report_dir(email, report_id)
    rdir.mkdir(parents=True, exist_ok=True)
    docx_path = rdir / "report.docx"
    docx_first_pass_saved = {"done": False}

    captured: list[dict] = []
    store = V4SessionStore()
    sid_holder = {"sid": None}

    class _Emitter:
        def emit(self, phase, message, *, data=None):
            captured.append({
                "ts": datetime.now(timezone.utc).isoformat(),
                "phase": phase,
                "message": message,
                "data": data,
            })
            # Checkpoint DOCX after first synth (mirror run2_baseline)
            if (
                not docx_first_pass_saved["done"]
                and phase == "bibliography"
                and "generated" in (message or "").lower()
                and sid_holder["sid"] is not None
            ):
                try:
                    sess_now = store.get(sid_holder["sid"])
                    if sess_now.final_report is not None:
                        render_docx(sess_now.final_report, docx_path)
                        docx_first_pass_saved["done"] = True
                except Exception:
                    pass

    orch = V4Orchestrator(store, mock=False, emitter=_Emitter())
    sid = uuid.uuid4().hex[:12]
    sid_holder["sid"] = sid
    store.create(session_id=sid, raw_question=payload.question)

    sess = store.get(sid)
    sess.source_reports = [
        UploadedMarkdown(
            filename=u.filename,
            content=u.content,
            detected_tool="other",
            word_count=len(u.content.split()),
        )
        for u in payload.uploads
    ]
    sess.status = "reports_uploaded" if sess.source_reports else "draft"
    store.update(sess)

    stages = {
        "prompt_master": SONNET,
        "analyzer": SONNET,
        "synthesizer": SONNET,
        "critic": SONNET,
    }
    _write_status(email, report_id, status="running", started_at=datetime.now(timezone.utc).isoformat())

    try:
        with patch.object(v4_module, "models_for_preference", lambda pref: stages):
            await orch.generate_prompt(sid)
            if sess.source_reports:
                await orch.analyze(sid)
                await orch.synthesize(sid)
            else:
                # No uploads yet — stop after PM, status=prompt_ready.
                _write_status(
                    email, report_id,
                    status="prompt_ready",
                    finished_at=datetime.now(timezone.utc).isoformat(),
                )
                return
    except Exception as e:
        _write_status(
            email, report_id,
            status="error",
            error=f"{type(e).__name__}: {e}",
            finished_at=datetime.now(timezone.utc).isoformat(),
        )
        log.exception("report %s failed: %s", report_id, e)
        return

    session = store.get(sid)
    final = session.final_report
    cost_usd = round(session.total_cost_rub / USD_RUB_RATE, 4)

    if final is not None:
        try:
            render_docx(final, docx_path)
        except Exception:
            log.exception("final docx render failed")

    audit = {
        "report_id": report_id,
        "email": email,
        "question": payload.question,
        "ran_at_utc": datetime.now(timezone.utc).isoformat(),
        "cost_usd": cost_usd,
        "cost_rub": round(session.total_cost_rub, 2),
        "uploads_count": len(payload.uploads),
        "source_count_in_final": len(final.all_sources) if final else 0,
        "evidence_grade_distribution": evidence_grade_distribution(final) if final else None,
        "evidence_quality": final.metadata.get("evidence_quality") if final else None,
        "main_synthesis_chars": len(final.main_synthesis) if final else 0,
    }
    (rdir / "audit_summary.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    with (rdir / "trace.jsonl").open("w", encoding="utf-8") as f:
        for ev in captured:
            f.write(json.dumps(ev, ensure_ascii=False, default=str) + "\n")

    _write_status(
        email, report_id,
        status="done" if final else "error",
        finished_at=datetime.now(timezone.utc).isoformat(),
        cost_usd=cost_usd,
        grades=audit["evidence_grade_distribution"],
        source_count=audit["source_count_in_final"],
        evidence_quality=audit["evidence_quality"],
    )


def _kick_background(email: str, report_id: str, payload: ReportIn) -> None:
    """Schedule _run_report_async on a fresh event loop in a daemon thread.

    BackgroundTasks would tie the report's lifetime to the request handler's
    lifecycle on some servers; running the v4 cycle (10-45 min) deserves a
    standalone thread that survives even if the original request is GCed.
    """
    def _runner():
        try:
            asyncio.run(_run_report_async(email, report_id, payload))
        except Exception:
            log.exception("background runner crashed")
    t = threading.Thread(target=_runner, name=f"report-{report_id}", daemon=True)
    t.start()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", response_model=ReportOut, status_code=202)
async def create_report(
    payload: ReportIn,
    request: Request,
    user: dict = Depends(require_user),
) -> ReportOut:
    report_id = uuid.uuid4().hex[:12]
    created_at = datetime.now(timezone.utc).isoformat()
    with _REPORTS_LOCK:
        _write_status(
            user["email"], report_id,
            id=report_id,
            status="queued",
            question=payload.question,
            created_at=created_at,
        )
    _kick_background(user["email"], report_id, payload)
    return ReportOut(id=report_id, status="queued", question=payload.question, created_at=created_at)


@router.get("", response_model=list[ReportOut])
async def list_reports(user: dict = Depends(require_user)) -> list[ReportOut]:
    udir = _user_dir(user["email"])
    if not udir.exists():
        return []
    out: list[ReportOut] = []
    for child in sorted(udir.iterdir(), reverse=True):
        if not child.is_dir():
            continue
        s = _read_status(user["email"], child.name)
        if not s:
            continue
        out.append(ReportOut(
            id=s.get("id", child.name),
            status=s.get("status", "unknown"),
            question=s.get("question", ""),
            created_at=s.get("created_at", ""),
            finished_at=s.get("finished_at"),
            cost_usd=s.get("cost_usd"),
            error=s.get("error"),
            grades=s.get("grades"),
            source_count=s.get("source_count"),
            evidence_quality=s.get("evidence_quality"),
        ))
    return out


@router.get("/{report_id}", response_model=ReportOut)
async def get_report(report_id: str, user: dict = Depends(require_user)) -> ReportOut:
    s = _read_status(user["email"], report_id)
    if not s:
        raise HTTPException(status_code=404, detail="report not found")
    return ReportOut(
        id=s.get("id", report_id),
        status=s.get("status", "unknown"),
        question=s.get("question", ""),
        created_at=s.get("created_at", ""),
        finished_at=s.get("finished_at"),
        cost_usd=s.get("cost_usd"),
        error=s.get("error"),
        grades=s.get("grades"),
        source_count=s.get("source_count"),
        evidence_quality=s.get("evidence_quality"),
    )


@router.get("/{report_id}/docx")
async def download_docx(report_id: str, user: dict = Depends(require_user)) -> FileResponse:
    s = _read_status(user["email"], report_id)
    if not s:
        raise HTTPException(status_code=404, detail="report not found")
    p = _report_dir(user["email"], report_id) / "report.docx"
    if not p.exists():
        raise HTTPException(status_code=404, detail="DOCX not yet rendered")
    return FileResponse(p, filename=f"smart_report_{report_id}.docx", media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
