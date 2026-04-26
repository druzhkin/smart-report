"""FastAPI router for v4 meta-analysis.

Track A implements:
    - POST /api/v4/sessions                         (create session)
    - POST /api/v4/sessions/{id}/generate-prompt    (run Prompt Master)

Track B fills:
    - POST /api/v4/sessions/{id}/upload-reports
    - POST /api/v4/sessions/{id}/analyze
    - POST /api/v4/sessions/{id}/upload-followup
    - POST /api/v4/sessions/{id}/synthesize
    - GET  /api/v4/sessions/{id}
    - GET  /api/v4/sessions/{id}/events
    - GET  /api/v4/sessions/{id}/export

Session + event state is kept in two module-level dicts; identical pattern to v3
jobs.py. That's fine for MVP (single uvicorn worker).
"""

from __future__ import annotations

import asyncio
import logging
import mimetypes
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import Literal

from ..events import ALLOWED_PHASES, EventEmitter
from ..exporters import (
    v4_to_report_dict,
    write_docx,
    write_gamma_pdf_stub,
    write_gamma_pptx_stub,
    write_json,
    write_md,
    write_onepager_html,
    write_pptx,
)
from ..io import RUNS_DIR
from ..follow_up_prompter import (
    DEFAULT_FOLLOW_UP_MODEL,
    generate_follow_up_prompts,
)
from ..gap_detector import detect_gaps, gap_count_by_severity
from ..models import (
    AnalysisOutput,
    DetectedTool,
    EvidenceGap,
    FinalReport,
    FollowUpPrompt,
    ResearchPrompt,
    UploadedMarkdown,
    V4Session,
)
from ..v4_orchestrator import V4Orchestrator, V4SessionStore

log = logging.getLogger("smart_report.api.v4")

router = APIRouter(prefix="/api/v4", tags=["v4"])


# ---- module-level state (v3-jobs.py style) ----

_V4_SESSIONS: dict[str, V4Session] = {}
_V4_EVENTS: dict[str, list[dict[str, Any]]] = {}
_V4_EVENT_SIGNALS: dict[str, asyncio.Event] = {}

# One shared V4SessionStore that reads/writes _V4_SESSIONS so every endpoint
# and any test-side monkeypatching of _V4_SESSIONS stays consistent.
class _DictBackedStore(V4SessionStore):
    def __init__(self, backing: dict[str, V4Session]) -> None:
        super().__init__()
        self._sessions = backing

# SaaS persistence: when DATABASE_URL is set (Railway PostgreSQL), use the
# Pg-backed store so sessions survive container restarts. Falls back to the
# in-memory dict-backed store for local dev / unit tests (where most callers
# monkeypatch _V4_SESSIONS directly).
from ..persistence import make_session_store as _make_session_store

_store = _make_session_store()
if isinstance(_store, V4SessionStore) and not isinstance(_store, _DictBackedStore):
    # in-memory path (DATABASE_URL absent) — wrap the dict so existing tests
    # that patch _V4_SESSIONS keep working.
    _store = _DictBackedStore(_V4_SESSIONS)


class _SessionEmitter(EventEmitter):
    """Append events to _V4_EVENTS[session_id]; fire signal for long-polling."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id

    def emit(
        self, phase: str, message: str, *, data: dict[str, Any] | None = None
    ) -> None:
        if phase not in ALLOWED_PHASES:
            phase = "status"
        events = _V4_EVENTS.setdefault(self.session_id, [])
        events.append(
            {
                "seq": len(events),
                "phase": phase,
                "message": message,
                "data": data,
                "ts": time.time(),
            }
        )
        sig = _V4_EVENT_SIGNALS.get(self.session_id)
        if sig is not None:
            sig.set()


# ---- request / response schemas ----


class CreateSessionIn(BaseModel):
    question: str = Field(..., min_length=3, max_length=8000)


class CreateSessionOut(BaseModel):
    session_id: str


class ModelPreferenceIn(BaseModel):
    model_preference: Literal["sonnet", "opus"] | None = None


# ---- endpoints ----


# ----- per-user ownership + cost cap helpers -----


def _current_email(request: Request) -> str | None:
    """Read auth cookie; returns user email if signed in, None for anonymous.

    Avoids hard import on smart_report.api.auth so unit tests that monkeypatch
    request.session keep working.
    """
    sess = getattr(request, "session", {}) or {}
    return sess.get("user_email")


def _require_email(request: Request) -> str:
    """Require an authenticated session — raise 401 otherwise.

    Used on POST /sessions so anonymous direct-API callers can't create
    publicly-readable sessions that bypass per-user isolation.
    """
    email = _current_email(request)
    if not email:
        raise HTTPException(
            status_code=401,
            detail="not authenticated — sign in or sign up first",
        )
    return email


def _ensure_owner(session, email: str | None) -> None:
    """Raise 403 if session is owner-tagged and the request's user doesn't match.

    Anonymous sessions (user_email=None) — only legacy rows from before
    SaaS auth landed. Treated as public for backwards-compat; new sessions
    always carry user_email because POST /sessions now requires auth.
    """
    owner = getattr(session, "user_email", None)
    if owner is None:
        return  # legacy/public session
    if email != owner:
        raise HTTPException(status_code=403, detail="not your session")


def _get_owned(session_id: str, request: Request):
    """Fetch session by id and check ownership in one call.

    404 if missing, 403 if owned by another user, returns V4Session otherwise.
    Use this in every /sessions/{session_id}/* handler.
    """
    try:
        session = _store.get(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"session {session_id} not found")
    _ensure_owner(session, _current_email(request))
    return session


# Cost cap — prevent abuse where a signed-up user spends unbounded LLM money.
# Read from env so ops can adjust without redeploy. Default $1.00/user/30d
# = ~2 reports — generous demo allowance, not real product pricing.
# $50/30d default — enough for ~25 Standard Valyu Research runs ($0.50 each)
# or ~3 Heavy ($2.50). Override via env var for stricter prod policy.
_USER_MONTHLY_CAP_USD: float = float(os.environ.get("USER_MONTHLY_CAP_USD", "50.0"))
_USD_RUB_RATE: float = 75.4


def _user_monthly_spend_usd(email: str) -> float:
    """Sum total_cost_rub across the user's sessions in the last 30 days,
    convert to USD. Uses store.all() — fine for demo scale (sub-1k sessions).
    For real scale move this to a SQL aggregate."""
    from datetime import datetime as _dt, timedelta as _td, timezone as _tz
    cutoff = _dt.now(_tz.utc) - _td(days=30)
    total_rub = 0.0
    for s in _store.all():
        if getattr(s, "user_email", None) != email:
            continue
        created = s.created_at
        # store may give a tz-naive datetime depending on backend
        if hasattr(created, "tzinfo") and created.tzinfo is None:
            created = created.replace(tzinfo=_tz.utc)
        if created < cutoff:
            continue
        total_rub += float(s.total_cost_rub or 0.0)
    return total_rub / _USD_RUB_RATE


def _enforce_cost_cap(email: str) -> None:
    """Raise 402 if the user is over their 30-day spend cap.

    Called pre-flight on /generate-prompt, /analyze, /synthesize — the three
    LLM-spending entry points. Lightweight cheap reads (whoami) stay free.
    """
    spent = _user_monthly_spend_usd(email)
    if spent >= _USER_MONTHLY_CAP_USD:
        raise HTTPException(
            status_code=402,
            detail=(
                f"monthly spend cap reached: ${spent:.2f} of "
                f"${_USER_MONTHLY_CAP_USD:.2f}. Contact support for a higher tier."
            ),
        )


def _owned_with_cap(session_id: str, request: Request):
    """Combined ownership check + cost cap enforcement for LLM-spending endpoints.

    Also rejects cancelled sessions with 409 — once cancelled, no further
    LLM-spending calls run on the session. The user can DELETE it or
    create a new one.
    """
    session = _get_owned(session_id, request)
    if getattr(session, "status", None) == "cancelled":
        raise HTTPException(
            status_code=409,
            detail="session was cancelled — create a new session to continue",
        )
    owner = getattr(session, "user_email", None)
    if owner:  # only enforce cap for authenticated owners (legacy public sessions skip)
        _enforce_cost_cap(owner)
    return session


@router.post("/sessions", response_model=CreateSessionOut)
async def create_session(payload: CreateSessionIn, request: Request) -> CreateSessionOut:
    # Auth required — closes the anonymous-session bypass that let direct
    # API callers create sessions readable by anyone with the session_id.
    # Frontend already gates /v4/* behind /login (commit 8874c90), so this
    # is the matching server-side enforcement.
    email = _require_email(request)
    # Cost cap pre-flight: even a fresh session counts because the next call
    # will be generate-prompt → Sonnet $$$.
    _enforce_cost_cap(email)
    session_id = uuid.uuid4().hex[:12]
    session = _store.create(session_id=session_id, raw_question=payload.question)
    session.user_email = email
    _store.update(session)
    _V4_EVENTS[session_id] = []
    _V4_EVENT_SIGNALS[session_id] = asyncio.Event()
    log.info("v4 session %s created (owner=%s)", session_id, email)
    return CreateSessionOut(session_id=session_id)


@router.get("/sessions")
async def list_my_sessions(request: Request) -> list[dict]:
    """List sessions owned by the current authenticated user.

    Anonymous callers get an empty list (cannot enumerate public sessions).
    """
    email = _current_email(request)
    if not email:
        return []
    out = []
    for s in _store.all():
        if s.user_email == email:
            out.append({
                "session_id": s.session_id,
                "raw_question": s.raw_question,
                "status": s.status,
                "created_at": s.created_at.isoformat() if hasattr(s.created_at, "isoformat") else s.created_at,
                "total_cost_rub": s.total_cost_rub,
                "has_final_report": s.final_report is not None,
            })
    out.sort(key=lambda r: r["created_at"], reverse=True)
    return out


# /admin/restore-session was an open POST that let any caller inject a
# V4Session JSON into the in-memory store. With Postgres persistence
# (commit d527551) the original recovery use-case (backend restart wipes
# RAM) no longer applies. Removed to close the injection surface — if
# manual ops recovery is ever needed, do it via direct DB access.


@router.post("/sessions/{session_id}/generate-prompt", response_model=ResearchPrompt)
async def generate_prompt(session_id: str, request: Request, payload: ModelPreferenceIn | None = None) -> ResearchPrompt:
    _owned_with_cap(session_id, request)
    orch = V4Orchestrator(_store, emitter=_SessionEmitter(session_id))
    model_preference = payload.model_preference if payload else None
    try:
        return await orch.generate_prompt(session_id, model_preference=model_preference)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        log.exception("v4 generate_prompt failed for %s", session_id)
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}") from e


# ---- Track B endpoints ----------------------------------------------------


@router.post("/sessions/{session_id}/upload-reports")
async def upload_reports(
    session_id: str, request: Request, files: list[UploadFile]
) -> list[dict[str, Any]]:
    _get_owned(session_id, request)
    return await _upload_markdown(session_id, files, dest="source")


@router.post("/sessions/{session_id}/upload-followup")
async def upload_followup(
    session_id: str, request: Request, files: list[UploadFile]
) -> list[dict[str, Any]]:
    _get_owned(session_id, request)
    return await _upload_markdown(session_id, files, dest="followup")


@router.post("/sessions/{session_id}/analyze", response_model=AnalysisOutput)
async def analyze(session_id: str, request: Request, payload: ModelPreferenceIn | None = None) -> AnalysisOutput:
    _owned_with_cap(session_id, request)
    orch = V4Orchestrator(_store, emitter=_SessionEmitter(session_id))
    model_preference = payload.model_preference if payload else None
    try:
        return await orch.analyze(session_id, model_preference=model_preference)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        log.exception("v4 analyze failed for %s", session_id)
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}") from e


class AutoDRIn(BaseModel):
    service: Literal["valyu", "tavily", "exa", "perplexity", "openai", "claude", "gemini"]
    prompt: str | None = Field(
        default=None,
        max_length=20000,
        description="Optional override; defaults to the session's research_prompt.full_prompt or raw_question.",
    )
    domain_hint: str | None = Field(default=None, max_length=64)
    # When set, routes through the service's async Research API:
    #   valyu:  fast/standard/heavy/max (Valyu Research, fixed $0.10-$15)
    #   tavily: mini/pro/auto (Tavily Research)
    #   exa:    fast/standard/pro (Exa research-fast/research/research-pro)
    # When None, falls back to instant search (legacy per-result pricing).
    mode: str | None = Field(default=None, max_length=64)


class AutoDROut(BaseModel):
    """Sync-instant result (Tavily/Exa/Perplexity, or Valyu legacy search).

    For async Valyu Research, the endpoint returns AutoDRAsyncOut instead.
    The frontend distinguishes by checking for `task_id`.
    """
    service: str
    filename: str
    word_count: int
    source_count: int
    cost_usd: float
    cost_rub: float
    notes: str
    task_id: str | None = None  # always None for sync path; helps frontend type-narrow


class AutoDRAsyncOut(BaseModel):
    """Async submission — frontend polls /auto-dr-status until done."""
    service: str
    mode: str
    task_id: str
    cost_usd: float
    cost_rub: float
    eta_min_low: int
    eta_min_high: int
    message: str


class AutoDRStatusOut(BaseModel):
    task_id: str
    state: str                                    # queued|running|completed|failed|cancelled
    progress_pct: int | None = None
    message: str | None = None
    # When state="completed", the rest of these are populated and the
    # session.source_reports has already been updated server-side.
    filename: str | None = None
    word_count: int | None = None
    source_count: int | None = None
    cost_usd: float | None = None
    cost_rub: float | None = None
    error: str | None = None


@router.post("/sessions/{session_id}/auto-dr")
async def auto_dr(session_id: str, request: Request, payload: AutoDRIn):
    """Run Deep Research via the chosen service.

    Two return shapes:
    - **AutoDROut** (sync): Tavily/Exa/Perplexity, or Valyu without `mode`
      param. Returns immediately with the result already appended to
      `session.source_reports`.
    - **AutoDRAsyncOut** (async): Valyu with `mode` ∈ {fast, standard,
      heavy, max} — uses Valyu Research API (fixed price, 5-180 min).
      Returns task_id immediately; frontend polls /auto-dr-status.

    Cost is charged to the user's monthly cap on submission for async
    (so a long-running heavy job can't be re-submitted forever) and on
    completion for sync.
    """
    session = _owned_with_cap(session_id, request)
    from ..sources.auto_dr import (
        AutoDRError, run_auto_dr, submit_async_research,
    )
    from ..sources.valyu_deepresearch import RESEARCH_MODE_PRICE_USD

    question = (payload.prompt or "").strip()
    if not question:
        if session.research_prompt and session.research_prompt.full_prompt:
            question = session.research_prompt.full_prompt
        else:
            question = session.raw_question

    emitter = _SessionEmitter(session_id)

    # --- Async path: Valyu / Tavily / Exa / OpenAI Research APIs ---
    if payload.mode is not None and payload.service in {"valyu", "tavily", "exa", "openai"}:
        mode = payload.mode
        svc_label = {
            "valyu": "Valyu Research",
            "tavily": "Tavily Research",
            "exa": "Exa Research",
            "openai": "OpenAI Deep Research",
        }[payload.service]
        emitter.emit(
            "status",
            f"Отправляю задачу в {svc_label} ({mode})…",
            data={"service": payload.service, "mode": mode},
        )
        try:
            sub = await submit_async_research(
                payload.service, question, mode=mode,
                session_id=session_id, store=_store,
            )
        except AutoDRError as e:
            emitter.emit("error", f"{svc_label}: {e}", data={"service": payload.service, "mode": mode})
            raise HTTPException(status_code=502, detail=str(e)) from e

        # Charge cost upfront — fixed-price job, billed regardless of completion.
        cost_rub = round(sub.cost_usd * _USD_RUB_RATE, 4)
        session.total_cost_rub = float(session.total_cost_rub or 0.0) + cost_rub
        session.pending_dr_jobs = list(session.pending_dr_jobs or []) + [{
            "task_id": sub.task_id,
            "service": payload.service,
            "mode": mode,
            "cost_usd": sub.cost_usd,
            "cost_rub": cost_rub,
            "submitted_at": time.time(),
        }]
        _store.update(session)

        emitter.emit(
            "status",
            f"{svc_label} запущен: задача {sub.task_id[:8]}…, режим {mode}, ETA {sub.eta_min_low}-{sub.eta_min_high} мин",
            data={"service": payload.service, "mode": mode, "task_id": sub.task_id},
        )

        return AutoDRAsyncOut(
            service=payload.service,
            mode=mode,
            task_id=sub.task_id,
            cost_usd=sub.cost_usd,
            cost_rub=cost_rub,
            eta_min_low=sub.eta_min_low,
            eta_min_high=sub.eta_min_high,
            message=(
                f"{svc_label} ({mode}) запущен. Ожидаемое время: "
                f"{sub.eta_min_low}–{sub.eta_min_high} минут. Стоимость: "
                f"${sub.cost_usd:.2f} (≈ ₽ {cost_rub:.2f}) — уже списана."
            ),
        )

    # --- Sync path: Tavily/Exa/Perplexity, or Valyu legacy search ---
    emitter.emit(
        "status",
        f"Запускаю Deep Research через {payload.service}…",
        data={"service": payload.service},
    )

    try:
        result = await run_auto_dr(
            payload.service,
            question,
            domain_hint=payload.domain_hint,
        )
    except AutoDRError as e:
        emitter.emit("error", f"{payload.service}: {e}", data={"service": payload.service})
        raise HTTPException(status_code=502, detail=str(e)) from e
    except Exception as e:
        log.exception("auto_dr unexpected failure for %s/%s", session_id, payload.service)
        emitter.emit("error", f"{payload.service} crashed: {e}", data={"service": payload.service})
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}") from e

    session.source_reports = list(session.source_reports) + [result.upload]
    if session.status in {"created", "prompt_generated"}:
        session.status = "reports_uploaded"
    session.total_cost_rub = float(session.total_cost_rub or 0.0) + result.cost_rub
    _store.update(session)

    emitter.emit(
        "status",
        f"{payload.service}: {result.source_count} источник(ов), ${result.cost_usd:.4f}",
        data={
            "service": payload.service,
            "cost_usd": result.cost_usd,
            "source_count": result.source_count,
        },
    )

    return AutoDROut(
        service=result.service,
        filename=result.upload.filename,
        word_count=result.upload.word_count,
        source_count=result.source_count,
        cost_usd=result.cost_usd,
        cost_rub=result.cost_rub,
        notes=result.notes,
    )


@router.post("/sessions/{session_id}/auto-dr-cancel")
async def auto_dr_cancel(session_id: str, request: Request, task_id: str) -> dict:
    """Cancel an in-flight async DR task.

    Currently only supports OpenAI DR (where we control the asyncio task).
    Valyu/Exa/Tavily Research run inside their respective SDKs — to cancel
    them properly we'd call the SDK's own cancel method, which is not yet
    wired. For now those services return 501.

    IMPORTANT: cancellation does NOT refund the API spend. If the request
    already reached the upstream provider, we paid for whatever tokens
    were generated. The cap charge stays.
    """
    session = _get_owned(session_id, request)
    job = next(
        (j for j in (session.pending_dr_jobs or []) if j.get("task_id") == task_id),
        None,
    )
    if job is None:
        raise HTTPException(status_code=404, detail=f"task_id {task_id} not found in this session")
    svc = job.get("service", "")
    if svc != "openai":
        raise HTTPException(
            status_code=501,
            detail=(
                f"cancel for {svc} is not yet implemented; the underlying SDK's "
                "cancel method needs to be wired. For OpenAI DR cancel works."
            ),
        )
    from ..sources.llm_deepresearch import cancel_openai_dr_task
    ok = cancel_openai_dr_task(task_id)
    if not ok:
        raise HTTPException(
            status_code=410,
            detail=(
                "task not in in-process registry — likely the container "
                "restarted; the API spend is forfeit and the task is lost."
            ),
        )
    # Remove from pending_dr_jobs so the UI no longer shows it.
    session.pending_dr_jobs = [
        j for j in (session.pending_dr_jobs or []) if j.get("task_id") != task_id
    ]
    _store.update(session)
    emitter = _SessionEmitter(session_id)
    emitter.emit(
        "status",
        f"OpenAI Deep Research отменён пользователем (task {task_id[:8]}…)",
        data={"service": "openai", "task_id": task_id, "reason": "user_cancel"},
    )
    return {"task_id": task_id, "state": "cancelled"}


@router.get("/sessions/{session_id}/auto-dr-status", response_model=AutoDRStatusOut)
async def auto_dr_status(session_id: str, request: Request, task_id: str) -> AutoDRStatusOut:
    """Poll the status of an async research job (Valyu Research).

    On state="completed", the markdown asset is fetched and prepended to
    session.source_reports server-side, then state stays "completed" on
    subsequent polls (the result is in source_reports, not duplicated).
    """
    session = _get_owned(session_id, request)
    job = next(
        (j for j in (session.pending_dr_jobs or []) if j.get("task_id") == task_id),
        None,
    )
    if job is None:
        raise HTTPException(status_code=404, detail=f"task_id {task_id} not found in this session")

    from ..sources.auto_dr import try_collect_async_research

    poll = await try_collect_async_research(
        task_id, service=job.get("service", "valyu"), mode=job.get("mode", "standard"),
    )

    out = AutoDRStatusOut(
        task_id=task_id,
        state=poll.state,
        progress_pct=poll.progress_pct,
        message=poll.message,
        error=poll.error,
    )

    if poll.state == "completed" and poll.result is not None:
        # Idempotency: only append to source_reports if not already there.
        already = any(
            u.filename == poll.result.upload.filename for u in session.source_reports
        )
        if not already:
            session.source_reports = list(session.source_reports) + [poll.result.upload]
            if session.status in {"created", "prompt_generated"}:
                session.status = "reports_uploaded"
            # Move the job out of pending → no need to bill again (already billed on submit).
            session.pending_dr_jobs = [
                j for j in (session.pending_dr_jobs or []) if j.get("task_id") != task_id
            ]
            _store.update(session)
            emitter = _SessionEmitter(session_id)
            emitter.emit(
                "status",
                f"Valyu Research завершён: {poll.result.source_count} источник(ов).",
                data={
                    "service": "valyu",
                    "task_id": task_id,
                    "source_count": poll.result.source_count,
                },
            )
        out.filename = poll.result.upload.filename
        out.word_count = poll.result.upload.word_count
        out.source_count = poll.result.source_count
        out.cost_usd = poll.result.cost_usd
        out.cost_rub = poll.result.cost_rub

    return out


@router.post("/sessions/{session_id}/synthesize", response_model=FinalReport)
async def synthesize(session_id: str, request: Request, payload: ModelPreferenceIn | None = None) -> FinalReport:
    _owned_with_cap(session_id, request)
    orch = V4Orchestrator(_store, emitter=_SessionEmitter(session_id))
    model_preference = payload.model_preference if payload else None
    try:
        return await orch.synthesize(session_id, model_preference=model_preference)
    except ValueError as e:
        log.exception("v4 synthesize ValueError for %s", session_id)
        raise HTTPException(status_code=400, detail=f"ValueError: {e}") from e
    except Exception as e:
        log.exception("v4 synthesize failed for %s", session_id)
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}") from e


# ---- Phase 2 Step 2.4 — Iterative Retrieval (manual loop) ----
# v4 has no auto-retrieval; "iterative" here means the analyst takes
# the follow-up prompts back to a DR tool and re-uploads results.
# Cap of 2 iterations to prevent infinite loops on hard-to-close gaps.

GAP_CHECK_ITERATION_CAP = 2


class CheckGapsResponse(BaseModel):
    iteration_number: int  # 1 or 2; >cap returns latest with can_iterate_more=False
    gaps: list[EvidenceGap]
    follow_up_prompts: list[FollowUpPrompt]
    gap_count_by_severity: dict[str, int]
    can_iterate_more: bool
    summary_for_analyst: str


@router.post(
    "/sessions/{session_id}/check-gaps",
    response_model=CheckGapsResponse,
)
async def check_gaps(session_id: str) -> CheckGapsResponse:
    """Surface evidence gaps + targeted follow-up DR prompts for this session.

    Requires that ``analyze`` already ran (the gap detector reads
    ``session.analysis``). If the Step 2.2 LLM planner produced
    ``sub_questions`` on the research prompt, the detector classifies
    each by authoritative-source coverage and the prompter writes one
    DR prompt for each actionable (critical / moderate) gap. Minor
    gaps are listed for transparency but no follow-up prompt is
    generated for them.

    The analyst takes ``follow_up_prompts`` to a DR tool, downloads
    the resulting reports, then re-uploads via /upload-reports +
    re-runs /analyze + /synthesize. Iteration is capped at 2.
    """
    if not _store.exists(session_id):
        raise HTTPException(status_code=404, detail=f"session {session_id} not found")
    session = _store.get(session_id)
    if session.analysis is None:
        raise HTTPException(
            status_code=400,
            detail="check-gaps requires a completed /analyze first",
        )

    # Increment first — the count of TIMES we returned a response is
    # what matters for the cap, not whether the response was useful.
    session.gap_check_iterations += 1
    iteration = session.gap_check_iterations
    can_iterate_more = iteration < GAP_CHECK_ITERATION_CAP

    sub_questions = (
        session.research_prompt.sub_questions if session.research_prompt else []
    )

    if not sub_questions:
        _store.update(session)
        return CheckGapsResponse(
            iteration_number=iteration,
            gaps=[],
            follow_up_prompts=[],
            gap_count_by_severity={"critical": 0, "moderate": 0, "minor": 0},
            can_iterate_more=can_iterate_more,
            summary_for_analyst=(
                "Декомпозиция запроса не использовалась (доменный шаблон или "
                "фактологический запрос). Проверка пробелов на уровне "
                "под-вопросов в этом режиме не применяется."
            ),
        )

    gaps = await detect_gaps(sub_questions, session.analysis)
    follow_ups = await generate_follow_up_prompts(
        gaps,
        original_query=session.raw_question,
        model=DEFAULT_FOLLOW_UP_MODEL,
    )
    counts = gap_count_by_severity(gaps)

    if not gaps:
        summary = (
            f"Итерация {iteration}: пробелов в доказательной базе не "
            f"обнаружено — все под-вопросы покрыты как минимум двумя "
            f"авторитетными источниками."
        )
    elif not can_iterate_more:
        summary = (
            f"Итерация {iteration} (последняя из {GAP_CHECK_ITERATION_CAP}): "
            f"найдено {len(gaps)} пробелов "
            f"(критичных: {counts['critical']}, умеренных: {counts['moderate']}, "
            f"незначительных: {counts['minor']}). Лимит итераций исчерпан — "
            f"оставшиеся пробелы фиксируются как ограничения отчёта."
        )
    else:
        summary = (
            f"Итерация {iteration} из {GAP_CHECK_ITERATION_CAP}: "
            f"найдено {len(gaps)} пробелов (критичных: {counts['critical']}, "
            f"умеренных: {counts['moderate']}, незначительных: {counts['minor']}). "
            f"Прогоните прилагаемые промпты в выбранных DR-инструментах "
            f"и загрузите результаты через /upload-reports + повторный "
            f"/analyze + /synthesize."
        )

    session.research_prompt = session.research_prompt.model_copy(
        update={"sub_questions": sub_questions}  # mutated in place by detect_gaps
    )
    _store.update(session)

    return CheckGapsResponse(
        iteration_number=iteration,
        gaps=gaps,
        follow_up_prompts=follow_ups,
        gap_count_by_severity=counts,
        can_iterate_more=can_iterate_more,
        summary_for_analyst=summary,
    )


@router.post("/sessions/{session_id}/cancel")
async def cancel_session(session_id: str, request: Request) -> dict:
    """Mark the session as cancelled and emit a cancel event.

    Best-effort: an in-flight LLM call still completes server-side (we
    pay for the in-flight tokens), but the session is flipped so any
    follow-up endpoint call is rejected and the UI can stop showing
    progress immediately. Idempotent — re-cancelling a cancelled session
    returns the same shape.
    """
    session = _get_owned(session_id, request)
    if session.status != "cancelled":
        session.status = "cancelled"
        _store.update(session)
        emitter = _SessionEmitter(session_id)
        emitter.emit("status", "Сессия отменена пользователем",
                     data={"reason": "user_cancel"})
    return {"session_id": session_id, "status": session.status}


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(session_id: str, request: Request):
    """Hard-delete a session and clear its in-memory event state.

    Owner-gated. Idempotent: deleting a missing session returns 404 so
    the user knows the call had no effect, instead of silently 204-ing.
    """
    _get_owned(session_id, request)
    _store.delete(session_id)
    _V4_EVENTS.pop(session_id, None)
    sig = _V4_EVENT_SIGNALS.pop(session_id, None)
    if sig is not None:
        sig.set()  # wake any long-poller so it returns immediately
    return None


@router.get("/sessions/{session_id}/quality")
async def get_quality_grade(session_id: str, request: Request) -> dict:
    """Compute the quality grade for a completed session.

    Returns 200 with grade='N/A' if synthesize hasn't run yet (rather than
    404) so the frontend can show a "still in progress" placeholder.
    """
    from ..quality_grade import compute_quality_grade
    session = _get_owned(session_id, request)
    return compute_quality_grade(session).to_dict()


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, request: Request) -> dict:
    s = _get_owned(session_id, request)
    return s.model_dump(mode="json")


@router.get("/sessions/{session_id}/events")
async def get_events(session_id: str, request: Request, since: int = 0, timeout: float = 25.0) -> dict:
    _get_owned(session_id, request)
    if session_id not in _V4_EVENTS:
        raise HTTPException(status_code=404, detail=f"session {session_id} not found")
    timeout = max(0.0, min(float(timeout), 30.0))
    sig = _V4_EVENT_SIGNALS.setdefault(session_id, asyncio.Event())
    if len(_V4_EVENTS[session_id]) <= since:
        sig.clear()
        try:
            await asyncio.wait_for(sig.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            pass
    events = _V4_EVENTS[session_id]
    new_events = events[since:]
    session = _store.get(session_id) if _store.exists(session_id) else None
    return {
        "events": new_events,
        "cursor": since + len(new_events),
        "status": session.status if session else None,
    }


_EXPORT_FORMATS = {"md", "json", "docx", "pptx", "onepager", "gamma-pptx", "gamma-pdf"}


@router.get("/sessions/{session_id}/export")
async def export_session(session_id: str, request: Request, format: str = "md") -> FileResponse:
    if format not in _EXPORT_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"unknown format {format!r}; allowed: {sorted(_EXPORT_FORMATS)}",
        )
    session = _get_owned(session_id, request)
    if session.final_report is None:
        raise HTTPException(
            status_code=409,
            detail=f"session {session_id} has no final_report yet; call /synthesize first",
        )

    out_dir = _session_artefact_dir(session_id)
    filename, writer, media_type = _export_handler(format)
    if format == "docx":
        # Use auto-selecting renderer (Node.js docx-js preferred, python-docx fallback)
        # — operates on the FinalReport directly, not the flattened report_dict.
        from smart_report.exporters import render_docx as _render_docx
        out_path = _render_docx(session.final_report, out_dir / filename)
    else:
        report_dict = v4_to_report_dict(session.final_report)
        out_path = writer(out_dir / filename, report_dict)
    return FileResponse(
        str(out_path),
        media_type=media_type,
        filename=filename,
    )


# ---- helpers --------------------------------------------------------------


_ALLOWED_SUFFIXES = {".md", ".markdown", ".txt"}


async def _upload_markdown(
    session_id: str, files: list[UploadFile], *, dest: str
) -> list[dict[str, Any]]:
    if not _store.exists(session_id):
        raise HTTPException(status_code=404, detail=f"session {session_id} not found")
    if not files:
        raise HTTPException(status_code=400, detail="no files uploaded")
    session = _store.get(session_id)
    persisted: list[UploadedMarkdown] = []
    for f in files:
        raw = await f.read()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("utf-8", errors="replace")
        filename = f.filename or "upload.md"
        suffix = Path(filename).suffix.lower()
        if suffix and suffix not in _ALLOWED_SUFFIXES:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"file {filename!r} has unsupported suffix {suffix!r}; "
                    f"allowed: {sorted(_ALLOWED_SUFFIXES)}"
                ),
            )
        um = UploadedMarkdown(
            filename=filename,
            content=text,
            detected_tool=_detect_tool(text, filename),
            word_count=len(re.findall(r"\S+", text)),
        )
        persisted.append(um)

    if dest == "source":
        session.source_reports = list(session.source_reports) + persisted
        session.status = "reports_uploaded"
    elif dest == "followup":
        session.followup_reports = list(session.followup_reports) + persisted
        session.status = "dobor_uploaded"
    else:
        raise ValueError(f"unknown dest: {dest!r}")
    _store.update(session)
    return [u.model_dump() for u in persisted]


_TOOL_MARKERS: dict[DetectedTool, tuple[str, ...]] = {
    "perplexity": ("perplexity", "sonar", "pplx", "pplx.ai"),
    "openai_dr": (
        "openai deep research",
        "openai dr",
        "chatgpt deep research",
        "o1-deep-research",
    ),
    "claude": ("claude", "anthropic"),
}


def _detect_tool(content: str, filename: str) -> DetectedTool | None:
    haystack = (content[:4000] + " " + filename).lower()
    for tool, markers in _TOOL_MARKERS.items():
        for m in markers:
            if m in haystack:
                return tool
    return "other"


def _session_artefact_dir(session_id: str) -> Path:
    d = RUNS_DIR / f"v4_{session_id}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _export_handler(format: str):
    """Return (filename, writer_fn, media_type) for a given format key."""
    if format == "md":
        return ("report.md", write_md, "text/markdown; charset=utf-8")
    if format == "json":
        return ("report.json", write_json, "application/json")
    if format == "docx":
        return (
            "report.docx",
            write_docx,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    if format == "pptx":
        return (
            "report.pptx",
            write_pptx,
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )
    if format == "onepager":
        return ("onepager.html", write_onepager_html, "text/html; charset=utf-8")
    if format == "gamma-pptx":
        return ("gamma-pptx.json", write_gamma_pptx_stub, "application/json")
    if format == "gamma-pdf":
        return ("gamma-pdf.json", write_gamma_pdf_stub, "application/json")
    raise HTTPException(status_code=400, detail=f"unknown format {format!r}")


# Keep MIME registry consistent on Windows where .md mimetypes return None.
mimetypes.add_type("text/markdown", ".md")
