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
import concurrent.futures as _cf
import csv
import io
import json
import logging
import mimetypes
import os
import re
import threading as _threading
import time
import uuid
import zipfile
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..adjudication_audit import assess_adjudication_quality
from ..analytic_closure import assess_analytic_closure
from ..analytic_depth import AnalyticDepthPlan, build_analytic_depth_plan
from ..evidence_audit import assess_evidence_support
from ..events import ALLOWED_PHASES, EventEmitter
from ..exporters import (
    assess_client_readiness,
    assess_premium_readiness,
    contains_client_leak,
    sanitize_final_report,
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
    DetectedTool,
    EvidenceGap,
    FinalReport,
    FollowUpPrompt,
    ResearchPrompt,
    UploadedMarkdown,
    V4Session,
)
from ..v4_orchestrator import V4Orchestrator, V4SessionStore
from ..visual_review import build_visual_review_gate

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


# ---- long-running task pattern (analyze / synthesize) ---------------------
# These orchestrator phases take 60-1800s on real prod data, but Cloudflare
# and Railway proxies kill HTTP connections at 100s. The endpoint returns
# 202 + task_id within <1s; the asyncio.Task runs in the background and
# writes terminal state to session.pending_long_tasks (PG-backed). Frontend
# polls /long-task-status for the verdict; the actual analysis/final_report
# payload lives on the session itself once the task completes.

# Long tasks run on a dedicated event loop in a daemon thread, NOT on the
# request-handler loop. Two reasons: (a) Starlette/anyio task groups cancel
# fire-and-forget children when the parent request ends, killing
# /analyze /synthesize mid-flight in TestClient and any "graceful shutdown"
# scenario; (b) keeping LLM/DB work off the request loop avoids competing
# with /events long-poll and /long-task-status latency budgets.
#
# Registry maps task_id → concurrent.futures.Future so we can probe
# liveness with .done() from any thread without crossing event-loop
# boundaries.

_LONG_TASK_REGISTRY: dict[str, "_cf.Future"] = {}
_BG_LOOP: asyncio.AbstractEventLoop | None = None
_BG_LOOP_LOCK = _threading.Lock()


def _get_bg_loop() -> asyncio.AbstractEventLoop:
    """Return the long-task event loop, lazily starting it on first use.

    Loop runs on a daemon thread, so it dies with the process. Handles
    re-creation if a prior loop got closed (e.g. test fixtures in some
    setups close all loops between tests).
    """
    global _BG_LOOP
    with _BG_LOOP_LOCK:
        if _BG_LOOP is None or _BG_LOOP.is_closed():
            loop = asyncio.new_event_loop()

            def _run_loop() -> None:
                asyncio.set_event_loop(loop)
                try:
                    loop.run_forever()
                finally:
                    loop.close()

            t = _threading.Thread(
                target=_run_loop, daemon=True, name="v4-long-tasks-loop"
            )
            t.start()
            _BG_LOOP = loop
        return _BG_LOOP


class LongTaskOut(BaseModel):
    """202 Accepted body returned by /analyze and /synthesize."""
    task_id: str
    phase: Literal["analyze", "synthesize", "export-pptx"]
    state: Literal["running"] = "running"
    started_at: str  # ISO8601 UTC


class LongTaskStatusOut(BaseModel):
    task_id: str
    phase: Literal["analyze", "synthesize", "export-pptx"]
    state: Literal["running", "completed", "failed"]
    started_at: str
    completed_at: str | None = None
    error: str | None = None


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


async def _run_long_task(
    session_id: str,
    task_id: str,
    phase: str,
    coro,
) -> None:
    """Wrapper that runs *coro* and records terminal state on the session.

    Catches BaseException (incl. CancelledError) so the durable
    pending_long_tasks entry always gets a verdict; without this a
    cancellation would leave the row stuck on `running` until reaped.
    """
    terminal: dict[str, Any] = {
        "state": "failed",
        "error": "task did not record terminal state",
    }
    try:
        await coro
        terminal = {"state": "completed", "error": None}
        log.info(
            "long-task %s phase=%s session=%s completed",
            task_id, phase, session_id,
        )
    except asyncio.CancelledError:
        terminal = {"state": "failed", "error": "task cancelled"}
        log.warning(
            "long-task %s phase=%s session=%s cancelled",
            task_id, phase, session_id,
        )
    except BaseException as e:  # noqa: BLE001 — we re-record below
        terminal = {"state": "failed", "error": f"{type(e).__name__}: {e}"}
        log.exception(
            "long-task %s phase=%s session=%s failed",
            task_id, phase, session_id,
        )
    finally:
        # Mirror terminal state to the durable list so subsequent polls
        # (and post-restart polls) see the verdict. _store.update is
        # sync DB I/O; on a non-request loop run_in_executor is fine.
        try:
            session = _store.get(session_id)
            updated = False
            for entry in session.pending_long_tasks or []:
                if entry.get("task_id") == task_id:
                    entry["state"] = terminal["state"]
                    entry["error"] = terminal["error"]
                    entry["completed_at"] = _now_iso()
                    updated = True
                    break
            if updated:
                await asyncio.get_event_loop().run_in_executor(
                    None, _store.update, session
                )
        except Exception:
            log.exception(
                "long-task %s: failed to record terminal state on session %s",
                task_id, session_id,
            )


def _has_running_long_task(session: V4Session, phase: str) -> str | None:
    """Return the task_id of an in-flight task for *phase*, or None."""
    for entry in session.pending_long_tasks or []:
        if entry.get("phase") == phase and entry.get("state") == "running":
            tid = entry.get("task_id")
            fut = _LONG_TASK_REGISTRY.get(tid)
            if fut is not None and not fut.done():
                return tid
    return None


def _phase_result_is_persisted(session: V4Session, phase: str) -> bool:
    """Return True when a long-task's durable output is already on session.

    Railway/container restarts can happen after the orchestrator commits
    analysis/final_report but before _run_long_task records the terminal
    pending_long_tasks verdict. In that case the in-memory Future is gone,
    but the task did not fail; the persisted artifact is the source of truth.
    """
    if phase == "analyze":
        return session.analysis is not None
    if phase == "synthesize":
        return session.final_report is not None
    return False


def _reap_stale_running_tasks(session: V4Session) -> bool:
    """Mark `running` entries with no live future as `failed`.

    Called on every status poll and submission. Necessary because Railway
    redeploys reset the in-memory registry but leave PG entries in
    `running` forever. Returns True if any entry was updated.
    """
    changed = False
    for entry in session.pending_long_tasks or []:
        if entry.get("state") != "running":
            continue
        tid = entry.get("task_id")
        fut = _LONG_TASK_REGISTRY.get(tid)
        if fut is None or fut.done():
            if _phase_result_is_persisted(session, entry.get("phase", "")):
                entry["state"] = "completed"
                entry["error"] = None
            else:
                entry["state"] = "failed"
                entry["error"] = (
                    entry.get("error")
                    or "container restart killed the task — re-run from the UI"
                )
            entry["completed_at"] = _now_iso()
            _LONG_TASK_REGISTRY.pop(tid, None)
            changed = True
    return changed


def _start_long_task(
    session: V4Session,
    *,
    phase: Literal["analyze", "synthesize", "export-pptx"],
    model_preference: str | None,
    coro_factory,
) -> LongTaskOut:
    """Submit a long-running orchestrator phase to the background loop.

    *coro_factory* is a zero-arg callable that returns the coroutine to run.
    The coroutine is scheduled on a dedicated daemon-thread event loop —
    NOT on the request handler's loop — so request lifecycle does not
    cancel it.
    """
    if _reap_stale_running_tasks(session):
        _store.update(session)

    in_flight = _has_running_long_task(session, phase)
    if in_flight is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"{phase} already running for this session "
                f"(task_id={in_flight}); poll /long-task-status or wait"
            ),
        )

    task_id = uuid.uuid4().hex
    started_at = _now_iso()
    entry = {
        "task_id": task_id,
        "phase": phase,
        "state": "running",
        "started_at": started_at,
        "completed_at": None,
        "error": None,
        "model_preference": model_preference,
    }
    session.pending_long_tasks = list(session.pending_long_tasks or []) + [entry]
    _store.update(session)

    fut = asyncio.run_coroutine_threadsafe(
        _run_long_task(session.session_id, task_id, phase, coro_factory()),
        _get_bg_loop(),
    )
    _LONG_TASK_REGISTRY[task_id] = fut

    return LongTaskOut(
        task_id=task_id,
        phase=phase,
        state="running",
        started_at=started_at,
    )


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
# Read from env so ops can adjust without redeploy.
# $500/30d default — this is an internal MVP, not a public self-serve SaaS.
# A low demo cap caused a paid DR run to complete, then blocked /analyze with
# 402, leaving the UI looking "stuck". Override USER_MONTHLY_CAP_USD in Railway
# for stricter public-demo policy. Set <=0 to disable the cap explicitly.
_USER_MONTHLY_CAP_USD: float = float(os.environ.get("USER_MONTHLY_CAP_USD", "500.0"))
from ..config import USD_RUB_RATE as _USD_RUB_RATE  # single source of truth


def _user_monthly_spend_usd(email: str) -> float:
    """Cost-cap pre-flight. Was a full-table scan + pydantic parse of EVERY
    session payload (5-30 sec block on 20+ sessions of 1-2MB each). Now
    uses store.monthly_spend_rub which is a single SQL aggregate
    (PG-backed) or a small in-memory loop (unit tests). Returns USD.
    """
    total_rub = _store.monthly_spend_rub(email, days=30)
    return total_rub / _USD_RUB_RATE


def _enforce_cost_cap(email: str) -> None:
    """Raise 402 if the user is over their 30-day spend cap.

    Called pre-flight on /generate-prompt, /analyze, /synthesize — the three
    LLM-spending entry points. Lightweight cheap reads (whoami) stay free.
    """
    spent = _user_monthly_spend_usd(email)
    if _USER_MONTHLY_CAP_USD <= 0:
        return
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


@router.post(
    "/sessions/{session_id}/analyze",
    response_model=LongTaskOut,
    status_code=202,
)
async def analyze(
    session_id: str, request: Request, payload: ModelPreferenceIn | None = None
) -> LongTaskOut:
    """Submit the analyzer phase as a background task.

    Returns 202 + task_id within <1s. The actual analyzer LLM call runs
    in an asyncio.Task; clients poll GET /long-task-status?task_id=...
    until state="completed", then read the AnalysisOutput from the
    session via GET /sessions/{id}.

    Pre-flight checks (cost cap, source_reports presence) run synchronously
    here so a missing-input misconfiguration surfaces as 400 instead of
    a deferred 'failed' verdict the user has to poll for.
    """
    session = _owned_with_cap(session_id, request)
    if not session.source_reports:
        raise HTTPException(
            status_code=400,
            detail="no source_reports to analyze — upload reports first",
        )
    model_preference = payload.model_preference if payload else None
    orch = V4Orchestrator(_store, emitter=_SessionEmitter(session_id))
    return _start_long_task(
        session,
        phase="analyze",
        model_preference=model_preference,
        coro_factory=lambda: orch.analyze(
            session_id, model_preference=model_preference
        ),
    )


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

    # --- Async path: Valyu / Tavily / Exa / OpenAI / Perplexity Research APIs ---
    if payload.mode is not None and payload.service in {"valyu", "tavily", "exa", "openai", "perplexity"}:
        mode = payload.mode
        svc_label = {
            "valyu": "Valyu Research",
            "tavily": "Tavily Research",
            "exa": "Exa Research",
            "openai": "OpenAI Deep Research",
            "perplexity": "Perplexity Deep Research",
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
        # For LLM DR (openai/perplexity), the streaming runner writes
        # partial_content here. Pre-populate the fields it expects.
        existing_jobs = list(session.pending_dr_jobs or [])
        existing_ids = {j.get("task_id") for j in existing_jobs}
        if sub.task_id not in existing_ids:
            existing_jobs.append({
            "task_id": sub.task_id,
            "service": payload.service,
            "mode": mode,
            "cost_usd": sub.cost_usd,
            "cost_rub": cost_rub,
            "submitted_at": time.time(),
            "state": "running",
            "partial_content": "",
            "partial_chars": 0,
            "last_progress_at": time.time(),
            })
        session.pending_dr_jobs = existing_jobs
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

    Per service:
    - openai: hard cancel — we own the asyncio.Task and can .cancel() it.
      The OpenAI tokens already generated are billed regardless.
    - valyu: hard cancel via valyu.deepresearch.cancel(task_id). The
      Valyu mode-flat fee is billed regardless of when we cancel.
    - tavily / exa: soft cancel — their SDKs don't expose a cancel method
      so the upstream task keeps running to completion. We just clean
      local state so the UI no longer shows it. Cost is billed in full.
    """
    session = _get_owned(session_id, request)
    job = next(
        (j for j in (session.pending_dr_jobs or []) if j.get("task_id") == task_id),
        None,
    )
    if job is None:
        raise HTTPException(status_code=404, detail=f"task_id {task_id} not found in this session")
    svc = job.get("service", "")
    cancel_kind = "soft"  # default; flipped to "hard" below if SDK supports it

    if svc in ("openai", "perplexity"):
        from ..sources.llm_deepresearch import cancel_openai_dr_task
        # If the asyncio.Task is alive, .cancel() it (hard cancel). If it's
        # not alive (e.g., already interrupted by container restart), just
        # clean the pending_dr_jobs entry below — soft cancel.
        alive = cancel_openai_dr_task(task_id)
        cancel_kind = "hard" if alive else "soft"
    elif svc == "valyu":
        # Valyu's SDK supports cancel(task_id). Best-effort — swallow errors.
        import os
        from ..sources.valyu_deepresearch import ValyuResearchClient
        api_key = os.environ.get("VALYU_API_KEY")
        if api_key:
            try:
                await ValyuResearchClient(api_key=api_key).cancel(task_id)
                cancel_kind = "hard"
            except Exception as e:
                log.warning("valyu cancel %s failed: %s", task_id, e)
                # fall through — soft cancel below
    elif svc in {"tavily", "exa"}:
        # SDK has no cancel method — soft cancel only.
        pass
    else:
        raise HTTPException(status_code=501, detail=f"cancel not supported for service {svc!r}")

    # Always remove the local job entry so the UI stops showing it.
    session.pending_dr_jobs = [
        j for j in (session.pending_dr_jobs or []) if j.get("task_id") != task_id
    ]
    _store.update(session)
    emitter = _SessionEmitter(session_id)
    note = (
        "отменён пользователем" if cancel_kind == "hard"
        else "отменён локально (upstream продолжит работать; деньги списались)"
    )
    emitter.emit(
        "status",
        f"{svc} DR {note} (task {task_id[:8]}…)",
        data={"service": svc, "task_id": task_id, "reason": "user_cancel", "kind": cancel_kind},
    )
    return {"task_id": task_id, "state": "cancelled", "kind": cancel_kind}


class AutoFollowupIn(BaseModel):
    service: Literal["valyu", "exa"] = "valyu"
    mode: str = "standard"


class AutoDepthLeadsIn(BaseModel):
    max_leads: int = Field(default=3, ge=1, le=8)
    include_priority: Literal["must", "should", "could", "all"] = "must"
    service_override: Literal["valyu", "tavily", "exa", "openai", "perplexity"] | None = None
    mode_override: str | None = Field(default=None, max_length=64)


class AutoDepthLeadOut(BaseModel):
    lead_id: str
    kind: str
    priority: str
    rationale: str = ""
    candidate_sources: list[str] = Field(default_factory=list)
    linked_to: list[str] = Field(default_factory=list)
    service: str
    mode: str
    task_id: str
    cost_usd: float
    cost_rub: float
    eta_min_low: int
    eta_min_high: int
    prompt_preview: str


class PremiumRefineIn(BaseModel):
    max_leads: int = Field(default=3, ge=1, le=8)
    include_priority: Literal["must", "should", "could", "all"] = "must"
    service_override: Literal["valyu", "tavily", "exa", "openai", "perplexity"] | None = None
    mode_override: str | None = Field(default=None, max_length=64)
    model_preference: str | None = Field(default=None, max_length=64)
    auto_synthesize: bool = True


class PremiumRefineOut(BaseModel):
    action: Literal[
        "wait_for_followups",
        "submitted_followups",
        "synthesize_started",
        "ready_or_blocked",
    ]
    message: str
    pending_task_ids: list[str] = Field(default_factory=list)
    submitted_leads: list[AutoDepthLeadOut] = Field(default_factory=list)
    synthesize_task: LongTaskOut | None = None
    analytic_closure: dict | None = None
    premium_readiness: dict | None = None


class PremiumRefinementStatusOut(BaseModel):
    recommended_action: Literal[
        "run_analysis",
        "wait_for_followups",
        "wait_for_synthesis",
        "submit_followups",
        "synthesize",
        "inspect_blockers",
        "ready",
    ]
    message: str
    pending_followup_task_ids: list[str] = Field(default_factory=list)
    running_synthesize_task_id: str | None = None
    final_report_needs_followup_resynthesis: bool = False
    analytic_closure: dict | None = None
    premium_readiness: dict | None = None
    next_research_leads: list[dict] = Field(default_factory=list)


def _lead_priority_allowed(lead_priority: str, include_priority: str) -> bool:
    if include_priority == "all":
        return True
    rank = {"must": 0, "should": 1, "could": 2}
    return rank.get(lead_priority, 9) <= rank.get(include_priority, 0)


def _async_service_for_lead(lead, domain_hint: str, override: str | None) -> str:
    if override:
        return override
    service = getattr(lead, "recommended_service", "manual")
    if service in {"valyu", "tavily", "exa", "openai", "perplexity"}:
        return service
    if domain_hint in {"financial_us", "scientific", "medical_clinical"}:
        return "valyu"
    return "perplexity"


def _next_research_leads_preview(plan: AnalyticDepthPlan, closure, *, limit: int = 5) -> list[dict]:
    closure_by_id = {
        item.lead_id: item
        for item in getattr(closure, "lead_closures", []) or []
    }
    previews: list[dict] = []
    for lead in plan.research_leads:
        if lead.priority not in {"must", "should"}:
            continue
        lead_closure = closure_by_id.get(lead.id)
        status = getattr(lead_closure, "status", "not_started") if lead_closure else "not_started"
        if status in {"closed", "partial"}:
            continue
        previews.append(
            {
                "lead_id": lead.id,
                "kind": lead.kind,
                "priority": lead.priority,
                "status": status,
                "service": _async_service_for_lead(lead, plan.domain_hint, None),
                "mode": lead.recommended_mode or "standard",
                "candidate_sources": list(lead.candidate_sources[:4]),
                "linked_to": list(lead.linked_to[:4]),
                "rationale": lead.rationale,
                "prompt_preview": _clip_text(lead.prompt, 320),
            }
        )
        if len(previews) >= limit:
            break
    return previews


def _clip_text(value: str, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _async_mode_for_lead(service: str, lead, override: str | None) -> str:
    allowed_by_service = {
        "perplexity": {"deep"},
        "openai": {"mini", "deep", "standard"},
        "valyu": {"standard", "fast", "deep"},
        "exa": {"standard", "fast"},
        "tavily": {"pro", "standard"},
    }
    allowed = allowed_by_service.get(service)
    fallback = {
        "valyu": "standard",
        "tavily": "pro",
        "exa": "standard",
        "openai": "mini",
        "perplexity": "deep",
    }.get(service, "standard")

    if override:
        normalized = override.strip().lower()
        if allowed is None or normalized in allowed:
            return normalized
        return fallback

    recommended = getattr(lead, "recommended_mode", None)
    if recommended and (allowed is None or recommended in allowed):
        return recommended
    return fallback


def _upsert_pending_dr_job(session, task_id: str, fields: dict) -> None:
    """Insert or update a pending DR job while preserving streaming fields.

    LLM DR backends pre-populate pending_dr_jobs before endpoints attach
    route-specific metadata. Updating in place avoids duplicate jobs and keeps
    partial_content/progress fields written by the background streamer.
    """
    jobs = list(session.pending_dr_jobs or [])
    for job in jobs:
        if job.get("task_id") == task_id:
            job.update(fields)
            session.pending_dr_jobs = jobs
            return
    jobs.append(fields)
    session.pending_dr_jobs = jobs


async def _submit_analytic_depth_leads(
    *,
    session_id: str,
    session: V4Session,
    plan: AnalyticDepthPlan,
    payload: AutoDepthLeadsIn | PremiumRefineIn,
) -> list[AutoDepthLeadOut]:
    from ..sources.auto_dr import AutoDRError, submit_async_research

    leads = [
        lead for lead in plan.research_leads
        if _lead_priority_allowed(lead.priority, payload.include_priority)
    ][: payload.max_leads]
    if not leads:
        return []

    emitter = _SessionEmitter(session_id)
    out: list[AutoDepthLeadOut] = []

    for lead in leads:
        service = _async_service_for_lead(lead, plan.domain_hint, payload.service_override)
        mode = _async_mode_for_lead(service, lead, payload.mode_override)
        try:
            sub = await submit_async_research(
                service,
                lead.prompt,
                mode=mode,
                session_id=session_id,
                store=_store,
            )
        except AutoDRError as e:
            emitter.emit(
                "error",
                f"Analytic lead {lead.id} submit failed: {e}",
                data={"lead_id": lead.id, "service": service, "mode": mode},
            )
            raise HTTPException(status_code=502, detail=str(e)) from e

        cost_rub = round(sub.cost_usd * _USD_RUB_RATE, 4)
        updated = _store.get(session_id)
        updated.total_cost_rub = float(updated.total_cost_rub or 0.0) + cost_rub
        _upsert_pending_dr_job(updated, sub.task_id, {
            "task_id": sub.task_id,
            "service": service,
            "mode": mode,
            "cost_usd": sub.cost_usd,
            "cost_rub": cost_rub,
            "submitted_at": time.time(),
            "state": "running",
            "is_followup": True,
            "analytic_depth": {
                "lead_id": lead.id,
                "kind": lead.kind,
                "priority": lead.priority,
                "rationale": lead.rationale,
                "candidate_sources": lead.candidate_sources,
                "linked_to": lead.linked_to,
            },
        })
        _store.update(updated)
        out.append(
            AutoDepthLeadOut(
                lead_id=lead.id,
                kind=lead.kind,
                priority=lead.priority,
                rationale=lead.rationale,
                candidate_sources=lead.candidate_sources,
                linked_to=lead.linked_to,
                service=service,
                mode=mode,
                task_id=sub.task_id,
                cost_usd=sub.cost_usd,
                cost_rub=cost_rub,
                eta_min_low=sub.eta_min_low,
                eta_min_high=sub.eta_min_high,
                prompt_preview=lead.prompt[:240],
            )
        )

    emitter.emit(
        "analytic_depth",
        f"Submitted {len(out)} analytic-depth research leads as async DR jobs.",
        data={
            "stage": "auto_depth_leads_submitted",
            "submitted": len(out),
            "task_ids": [item.task_id for item in out],
            "lead_ids": [item.lead_id for item in out],
            "services": [item.service for item in out],
            "cost_rub": round(sum(item.cost_rub for item in out), 4),
        },
    )
    return out


@router.post(
    "/sessions/{session_id}/auto-depth-leads",
    response_model=list[AutoDepthLeadOut],
)
async def auto_depth_leads(
    session_id: str,
    request: Request,
    payload: AutoDepthLeadsIn,
) -> list[AutoDepthLeadOut]:
    """Submit selected analytic-depth research leads as async DR jobs.

    This is the first executable iterative-retrieval loop: the system turns
    conflicts, gaps, unverified numbers, and disconfirming probes into concrete
    research jobs, records lead metadata on each pending job, and lets the
    existing /auto-dr-status collector ingest the results.
    """
    session = _owned_with_cap(session_id, request)
    if session.analysis is None:
        raise HTTPException(
            status_code=400,
            detail="auto-depth-leads requires a completed /analyze first",
        )

    plan = build_analytic_depth_plan(
        session.raw_question,
        analysis=session.analysis,
        report=session.final_report,
    )
    return await _submit_analytic_depth_leads(
        session_id=session_id,
        session=session,
        plan=plan,
        payload=payload,
    )


@router.post("/sessions/{session_id}/auto-followup", response_model=AutoDRAsyncOut)
async def auto_followup(session_id: str, request: Request, payload: AutoFollowupIn) -> AutoDRAsyncOut:
    """Fire ONE Valyu Standard (default) on the entire followup_prompt.

    The followup prompt produced by analyzer is already structured with
    `## Conflict:` / `## Gap:` headers — Standard agent reads the structure
    and addresses every section in one coherent document. Per-section split
    into N×Fast was rejected: at 5+ gaps Standard is cheaper ($0.50 vs
    $0.60), produces coherent output for synthesize (vs N fragmented
    docs), and the UI is simpler (1 progress bar, 1 retry, 1 cancel).

    Result lands in `session.followup_reports` (not source_reports) via
    `is_followup=True` on the pending_dr_jobs entry — auto_dr_status
    routes by that flag.
    """
    session = _owned_with_cap(session_id, request)
    if session.analysis is None or session.analysis.followup_prompt is None:
        raise HTTPException(
            status_code=400,
            detail="auto-followup requires a completed /analyze with a followup_prompt",
        )

    prompt = session.analysis.followup_prompt.prompt
    if not prompt.strip():
        raise HTTPException(status_code=400, detail="followup_prompt is empty")

    from ..sources.auto_dr import submit_async_research, AutoDRError

    svc_label = {"valyu": "Valyu Research", "exa": "Exa Research"}.get(
        payload.service, payload.service
    )
    emitter = _SessionEmitter(session_id)
    emitter.emit(
        "status",
        f"Запускаю {svc_label} ({payload.mode}) на followup-добор…",
        data={"service": payload.service, "mode": payload.mode, "is_followup": True},
    )

    try:
        sub = await submit_async_research(
            payload.service, prompt, mode=payload.mode,
            session_id=session_id, store=_store,
        )
    except AutoDRError as e:
        emitter.emit("error", f"{svc_label} (followup): {e}",
                     data={"service": payload.service, "mode": payload.mode})
        raise HTTPException(status_code=502, detail=str(e)) from e

    cost_rub = round(sub.cost_usd * _USD_RUB_RATE, 4)
    session = _store.get(session_id)
    # LLM DR backends may pre-populate pending_dr_jobs before this endpoint
    # attaches follow-up routing metadata. Update in place when present.
    _upsert_pending_dr_job(session, sub.task_id, {
        "task_id": sub.task_id,
        "service": payload.service,
        "mode": payload.mode,
        "cost_usd": sub.cost_usd,
        "cost_rub": cost_rub,
        "submitted_at": time.time(),
        "state": "running",
        "is_followup": True,
    })
    session.total_cost_rub = float(session.total_cost_rub or 0.0) + cost_rub
    _store.update(session)

    emitter.emit(
        "status",
        f"{svc_label} ({payload.mode}) на добор запущен: задача {sub.task_id[:8]}…, "
        f"ETA {sub.eta_min_low}-{sub.eta_min_high} мин",
        data={"service": payload.service, "mode": payload.mode,
              "task_id": sub.task_id, "is_followup": True},
    )

    return AutoDRAsyncOut(
        service=payload.service,
        mode=payload.mode,
        task_id=sub.task_id,
        cost_usd=sub.cost_usd,
        cost_rub=cost_rub,
        eta_min_low=sub.eta_min_low,
        eta_min_high=sub.eta_min_high,
        message=(
            f"{svc_label} ({payload.mode}) на добор запущен. ETA "
            f"{sub.eta_min_low}–{sub.eta_min_high} мин. Стоимость: "
            f"${sub.cost_usd:.2f} (≈ ₽ {cost_rub:.2f}) — уже списана."
        ),
    )


@router.post("/sessions/{session_id}/auto-dr-accept-partial")
async def auto_dr_accept_partial(session_id: str, request: Request, task_id: str) -> dict:
    """Accept a partial LLM DR result as a source_report.

    Used when an LLM DR (OpenAI / Perplexity) was interrupted by container
    restart and the user wants to keep the partial markdown rather than
    re-submitting from scratch.
    """
    session = _get_owned(session_id, request)
    from ..sources.llm_deepresearch import accept_partial_into_source_reports
    ok = accept_partial_into_source_reports(session, task_id)
    if not ok:
        raise HTTPException(status_code=404, detail="task or partial_content not found")
    _store.update(session)
    emitter = _SessionEmitter(session_id)
    emitter.emit("status", f"Частичный результат принят (task {task_id[:8]}…)",
                 data={"task_id": task_id, "action": "accept_partial"})
    return {"task_id": task_id, "ok": True}


@router.post("/sessions/{session_id}/auto-dr-resume", response_model=AutoDRAsyncOut)
async def auto_dr_resume(session_id: str, request: Request, task_id: str) -> AutoDRAsyncOut:
    """Resume an interrupted LLM DR by submitting a continuation prompt.

    Reads the partial_content + original mode/service, drops the old job
    from pending_dr_jobs, submits a fresh task with a "continue from here"
    prompt. New cost is charged.
    """
    session = _owned_with_cap(session_id, request)
    job = next(
        (j for j in (session.pending_dr_jobs or []) if j.get("task_id") == task_id),
        None,
    )
    if job is None:
        raise HTTPException(status_code=404, detail=f"task_id {task_id} not found")
    if job.get("service") not in ("openai", "perplexity"):
        raise HTTPException(
            status_code=400,
            detail="resume is only available for openai / perplexity LLM DR tasks",
        )

    partial = (job.get("partial_content") or "").strip()
    service = job.get("service")
    mode = job.get("mode", "mini" if service == "openai" else "deep")

    # Build a continuation prompt
    raw_q = session.raw_question
    if session.research_prompt and session.research_prompt.full_prompt:
        raw_q = session.research_prompt.full_prompt
    continue_prompt = (
        f"{raw_q}\n\n"
        f"## Continue from where the previous attempt left off\n"
        f"The previous response was interrupted. The text so far is below — "
        f"continue it without repeating, and produce a complete report.\n\n"
        f"---\n\n{partial}"
    )

    # Drop the old job (so it's not double-counted)
    session.pending_dr_jobs = [
        j for j in (session.pending_dr_jobs or []) if j.get("task_id") != task_id
    ]
    _store.update(session)

    # Submit a fresh one
    from ..sources.auto_dr import submit_async_research, AutoDRError
    try:
        sub = await submit_async_research(
            service, continue_prompt, mode=mode,
            session_id=session_id, store=_store,
        )
    except AutoDRError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    cost_rub = round(sub.cost_usd * _USD_RUB_RATE, 4)
    session.total_cost_rub = float(session.total_cost_rub or 0.0) + cost_rub
    session.pending_dr_jobs = list(session.pending_dr_jobs or []) + [{
        "task_id": sub.task_id,
        "service": service,
        "mode": mode,
        "model": "(see job runner)",
        "cost_usd": sub.cost_usd,
        "cost_rub": cost_rub,
        "submitted_at": time.time(),
        "state": "running",
        "partial_content": "",
        "partial_chars": 0,
        "last_progress_at": time.time(),
        "resumed_from": task_id,
    }]
    _store.update(session)
    emitter = _SessionEmitter(session_id)
    emitter.emit("status", f"Возобновлено: новый task_id {sub.task_id[:8]}…",
                 data={"original_task_id": task_id, "new_task_id": sub.task_id})

    return AutoDRAsyncOut(
        service=service, mode=mode, task_id=sub.task_id,
        cost_usd=sub.cost_usd, cost_rub=cost_rub,
        eta_min_low=sub.eta_min_low, eta_min_high=sub.eta_min_high,
        message=(
            f"Возобновлено как новая задача. ETA: "
            f"{sub.eta_min_low}–{sub.eta_min_high} мин. Стоимость: "
            f"${sub.cost_usd:.2f} (≈ ₽ {cost_rub:.2f}) — уже списана."
        ),
    )


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
        # For LLM DR (openai/perplexity), the streaming runner moves the
        # result into source_reports or followup_reports AND removes the
        # pending entry on completion. So "not found in pending" + "matching
        # upload exists" = silently completed. Surface as state=completed so
        # the frontend shows success instead of "task lost".
        prefix = task_id[:8]
        for svc_guess in ("openai", "perplexity"):
            candidates = [
                (session.source_reports or [], f"auto_dr_{svc_guess}_{prefix}.md"),
                (session.source_reports or [], f"auto_dr_{svc_guess}_{prefix}_partial.md"),
                (session.followup_reports or [], f"auto_followup_{svc_guess}_{prefix}.md"),
                (session.followup_reports or [], f"auto_followup_{svc_guess}_{prefix}_partial.md"),
            ]
            for uploads, expected_filename in candidates:
                for u in uploads:
                    if u.filename == expected_filename:
                        return AutoDRStatusOut(
                            task_id=task_id, state="completed",
                            filename=u.filename,
                            word_count=u.word_count,
                            source_count=0,
                            cost_usd=None,
                            cost_rub=None,
                        )
        raise HTTPException(status_code=404, detail=f"task_id {task_id} not found in this session")

    from ..sources.auto_dr import (
        try_collect_async_research, try_collect_async_research_from_session,
    )

    svc = job.get("service", "valyu")
    if svc in ("openai", "perplexity"):
        # Durable LLM DR: state lives in session.pending_dr_jobs (PG-backed).
        poll = try_collect_async_research_from_session(session, task_id)
    else:
        poll = await try_collect_async_research(
            task_id, service=svc, mode=job.get("mode", "standard"),
        )

    out = AutoDRStatusOut(
        task_id=task_id,
        state=poll.state,
        progress_pct=poll.progress_pct,
        message=poll.message,
        error=poll.error,
    )

    # Auto-clean orphaned pending_dr_jobs entry on terminal-failure states.
    # Keeps the session list tidy and lets the user retry without manual cleanup.
    if poll.state in {"failed", "cancelled"} and poll.error != "interrupted_with_partial":
        session.pending_dr_jobs = [
            j for j in (session.pending_dr_jobs or []) if j.get("task_id") != task_id
        ]
        _store.update(session)
    elif poll.error == "interrupted_with_partial":
        _store.update(session)

    if poll.state == "completed" and poll.result is not None:
        # Followup auto-DR results go to session.followup_reports;
        # first-pass DR goes to source_reports. Routed by is_followup flag.
        is_followup = bool(job.get("is_followup"))
        bucket = session.followup_reports if is_followup else session.source_reports
        already = any(
            u.filename == poll.result.upload.filename for u in (bucket or [])
        )
        # Rewrite filename for ANY followup result to a uniform
        # `auto_followup_<svc>_<id>.md` form. Valyu's wrapper produces
        # `valyu_research_<mode>_<id>.md` and the LLM-DR path produces
        # `auto_dr_<svc>_<id>.md` — both get normalised so the chat UI
        # shows a "followup" prefix consistently.
        if is_followup:
            poll.result.upload.filename = f"auto_followup_{job.get('service','svc')}_{task_id[:8]}.md"
            poll.result.upload = _with_analytic_depth_header(poll.result.upload, job)
            already = any(u.filename == poll.result.upload.filename for u in (bucket or []))
        if not already:
            if is_followup:
                session.followup_reports = list(session.followup_reports or []) + [poll.result.upload]
                if session.status in {"created", "prompt_generated", "reports_uploaded", "analyzed"}:
                    session.status = "dobor_uploaded"
            else:
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
                f"{'Followup' if is_followup else 'Valyu Research'} завершён: {poll.result.source_count} источник(ов).",
                data={
                    "service": "valyu",
                    "task_id": task_id,
                    "is_followup": is_followup,
                    "source_count": poll.result.source_count,
                },
            )
        out.filename = poll.result.upload.filename
        out.word_count = poll.result.upload.word_count
        out.source_count = poll.result.source_count
        out.cost_usd = poll.result.cost_usd
        out.cost_rub = poll.result.cost_rub

    return out


def _with_analytic_depth_header(upload: UploadedMarkdown, job: dict) -> UploadedMarkdown:
    meta = job.get("analytic_depth") or {}
    lead_id = str(meta.get("lead_id") or "").strip()
    if not lead_id:
        return upload
    if f"Smart Report analytic-depth lead: {lead_id}" in (upload.content or ""):
        return upload
    header = [
        "<!-- Smart Report analytic-depth metadata",
        f"Smart Report analytic-depth lead: {lead_id}",
        f"Kind: {meta.get('kind') or ''}",
        f"Priority: {meta.get('priority') or ''}",
        f"Rationale: {meta.get('rationale') or ''}",
        "Candidate sources: "
        + ", ".join(str(item) for item in (meta.get("candidate_sources") or []) if item),
        "Linked to: "
        + ", ".join(str(item) for item in (meta.get("linked_to") or []) if item),
        "-->",
        "",
    ]
    content = "\n".join(header) + (upload.content or "")
    return UploadedMarkdown(
        filename=upload.filename,
        content=content,
        detected_tool=upload.detected_tool,
        word_count=len(content.split()),
    )


@router.post(
    "/sessions/{session_id}/synthesize",
    response_model=LongTaskOut,
    status_code=202,
)
async def synthesize(
    session_id: str, request: Request, payload: ModelPreferenceIn | None = None
) -> LongTaskOut:
    """Submit the synthesizer phase as a background task.

    Returns 202 + task_id within <1s. The synthesizer LLM call (often
    300-1800s on real prod data, 30+ minutes on retry-loops) runs in
    an asyncio.Task. Clients poll GET /long-task-status?task_id=...
    and read the FinalReport from session.final_report on completion.
    """
    session = _owned_with_cap(session_id, request)
    if session.analysis is None:
        raise HTTPException(
            status_code=400,
            detail="analyze must run before synthesize",
        )
    model_preference = payload.model_preference if payload else None
    orch = V4Orchestrator(_store, emitter=_SessionEmitter(session_id))
    return _start_long_task(
        session,
        phase="synthesize",
        model_preference=model_preference,
        coro_factory=lambda: orch.synthesize(
            session_id, model_preference=model_preference
        ),
    )


@router.get(
    "/sessions/{session_id}/long-task-status",
    response_model=LongTaskStatusOut,
)
async def long_task_status(
    session_id: str, task_id: str, request: Request
) -> LongTaskStatusOut:
    """Poll the verdict for an /analyze or /synthesize background task.

    Returns the task's current state. On state="completed", clients
    should fetch GET /sessions/{id} to read the actual analysis or
    final_report payload. Live progress messages are surfaced via the
    existing /events long-poll, not via this endpoint.

    Reaps stale `running` entries (tasks killed by a container restart)
    before responding, so post-redeploy polls observe `failed` instead
    of being stuck on `running` forever.
    """
    session = _get_owned(session_id, request)
    if _reap_stale_running_tasks(session):
        await asyncio.to_thread(_store.update, session)
    entry = next(
        (
            e for e in (session.pending_long_tasks or [])
            if e.get("task_id") == task_id
        ),
        None,
    )
    if entry is None:
        raise HTTPException(
            status_code=404,
            detail=f"task_id {task_id} not found on this session",
        )
    return LongTaskStatusOut(
        task_id=entry["task_id"],
        phase=entry["phase"],
        state=entry["state"],
        started_at=entry["started_at"],
        completed_at=entry.get("completed_at"),
        error=entry.get("error"),
    )


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


@router.get("/sessions/{session_id}/analytic-depth", response_model=AnalyticDepthPlan)
async def get_analytic_depth_plan(session_id: str, request: Request) -> AnalyticDepthPlan:
    """Return the non-linear research map for a completed analysis.

    This is a read-only planning endpoint for the premium pipeline. It exposes
    the issue tree, competing hypotheses, disconfirming probes, benchmark
    questions, and prioritized research leads that can later drive selective
    follow-up retrieval. It intentionally does not mutate the legacy v4 session.
    """
    session = _get_owned(session_id, request)
    if session.analysis is None:
        raise HTTPException(
            status_code=409,
            detail=f"session {session_id} has no analysis yet; call /analyze first",
        )
    return build_analytic_depth_plan(
        session.raw_question,
        analysis=session.analysis,
        report=session.final_report,
    )


@router.get("/sessions/{session_id}/analytic-closure")
async def get_analytic_closure(session_id: str, request: Request) -> dict:
    """Return closure scoring for analytic-depth follow-up research.

    This does not mutate the session and does not pretend to prove correctness.
    It checks whether uploaded/generated follow-up reports appear to address
    the priority research leads with URLs, numbers, source language, and
    conflict-adjudication signals.
    """
    session = _get_owned(session_id, request)
    if session.analysis is None:
        raise HTTPException(
            status_code=409,
            detail=f"session {session_id} has no analysis yet; call /analyze first",
        )
    client_report = (
        sanitize_final_report(session.final_report)
        if session.final_report is not None
        else None
    )
    depth_plan = build_analytic_depth_plan(
        session.raw_question,
        analysis=session.analysis,
        report=client_report,
    )
    return assess_analytic_closure(
        depth_plan,
        list(session.followup_reports or []),
    ).model_dump(mode="json")


@router.get("/sessions/{session_id}/next-research-brief")
async def get_next_research_brief(session_id: str, request: Request) -> FileResponse:
    """Download the executable next-research brief without building a ZIP.

    This can be used immediately after /analyze, before a final report exists.
    It is the handoff artifact for a human analyst or another research agent:
    open analytic-depth leads, prompts, candidate sources, and current closure
    status.
    """
    session = _get_owned(session_id, request)
    if session.analysis is None:
        raise HTTPException(
            status_code=409,
            detail=f"session {session_id} has no analysis yet; call /analyze first",
        )
    client_report = (
        sanitize_final_report(session.final_report)
        if session.final_report is not None
        else None
    )
    out_path = _write_next_research_brief_file(
        _session_artefact_dir(session_id) / "next_research_brief.md",
        session,
        client_report,
    )
    return FileResponse(
        str(out_path),
        media_type="text/markdown; charset=utf-8",
        filename="next_research_brief.md",
    )


@router.get("/sessions/{session_id}/premium-readiness")
async def get_premium_readiness(session_id: str, request: Request) -> dict:
    """Return the stricter paid-report readiness gate.

    This is deliberately separate from the normal client-readiness gate. A
    report can be safe to export but still not good enough for a 20+ page
    paid analytical package.
    """
    session = _get_owned(session_id, request)
    if session.final_report is None:
        raise HTTPException(
            status_code=409,
            detail=f"session {session_id} has no final_report yet; call /synthesize first",
        )
    client_report = sanitize_final_report(session.final_report)
    depth_plan = (
        build_analytic_depth_plan(
            session.raw_question,
            analysis=session.analysis,
            report=client_report,
        )
        if session.analysis is not None
        else None
    )
    closure_report = (
        assess_analytic_closure(depth_plan, list(session.followup_reports or []))
        if depth_plan is not None
        else None
    )
    return assess_premium_readiness(
        client_report,
        analysis=session.analysis,
        depth_plan=depth_plan,
        closure_report=closure_report,
        evidence_audit=assess_evidence_support(client_report, session.analysis),
        adjudication_audit=assess_adjudication_quality(client_report, session.analysis),
    ).model_dump()


def _pending_followup_task_ids(session: V4Session) -> list[str]:
    return [
        str(job.get("task_id"))
        for job in (session.pending_dr_jobs or [])
        if job.get("is_followup") and job.get("state", "running") == "running"
    ]


def _final_report_needs_followup_resynthesis(session: V4Session) -> bool:
    if session.final_report is None:
        return True
    metadata = session.final_report.metadata or {}
    synthesized_followups = int(metadata.get("followup_reports_count") or 0)
    return synthesized_followups < len(session.followup_reports or [])


def _build_premium_refinement_status(session: V4Session) -> PremiumRefinementStatusOut:
    if session.analysis is None:
        return PremiumRefinementStatusOut(
            recommended_action="run_analysis",
            message="Run /analyze before premium refinement can inspect gaps and evidence.",
        )

    client_report = (
        sanitize_final_report(session.final_report)
        if session.final_report is not None
        else None
    )
    plan = build_analytic_depth_plan(
        session.raw_question,
        analysis=session.analysis,
        report=client_report,
    )
    closure = assess_analytic_closure(plan, list(session.followup_reports or []))
    pending_followups = _pending_followup_task_ids(session)
    running_synth = _has_running_long_task(session, "synthesize")
    needs_resynthesis = _final_report_needs_followup_resynthesis(session)

    readiness = None
    if session.final_report is not None:
        report_for_readiness = sanitize_final_report(session.final_report)
        readiness = assess_premium_readiness(
            report_for_readiness,
            analysis=session.analysis,
            depth_plan=plan,
            closure_report=closure,
            evidence_audit=assess_evidence_support(report_for_readiness, session.analysis),
            adjudication_audit=assess_adjudication_quality(report_for_readiness, session.analysis),
        ).model_dump()

    closure_dict = closure.model_dump(mode="json")
    next_research_leads = _next_research_leads_preview(plan, closure)
    if pending_followups:
        return PremiumRefinementStatusOut(
            recommended_action="wait_for_followups",
            message="Follow-up research is running; keep polling /auto-dr-status.",
            pending_followup_task_ids=pending_followups,
            running_synthesize_task_id=running_synth,
            final_report_needs_followup_resynthesis=needs_resynthesis,
            analytic_closure=closure_dict,
            premium_readiness=readiness,
            next_research_leads=next_research_leads,
        )
    if running_synth:
        return PremiumRefinementStatusOut(
            recommended_action="wait_for_synthesis",
            message="Synthesis is running; keep polling /long-task-status.",
            running_synthesize_task_id=running_synth,
            final_report_needs_followup_resynthesis=needs_resynthesis,
            analytic_closure=closure_dict,
            premium_readiness=readiness,
            next_research_leads=next_research_leads,
        )
    open_leads = int(closure.not_started or 0) + int(closure.not_closed or 0)
    if open_leads:
        return PremiumRefinementStatusOut(
            recommended_action="submit_followups",
            message=f"{open_leads} priority analytic-depth lead(s) still need follow-up evidence.",
            final_report_needs_followup_resynthesis=needs_resynthesis,
            analytic_closure=closure_dict,
            premium_readiness=readiness,
            next_research_leads=next_research_leads,
        )
    if needs_resynthesis:
        return PremiumRefinementStatusOut(
            recommended_action="synthesize",
            message="Follow-up evidence exists but the final report has not incorporated it yet.",
            final_report_needs_followup_resynthesis=True,
            analytic_closure=closure_dict,
            premium_readiness=readiness,
            next_research_leads=next_research_leads,
        )
    if readiness and not readiness.get("ready"):
        return PremiumRefinementStatusOut(
            recommended_action="inspect_blockers",
            message="Automatic research loop is closed; inspect premium readiness blockers.",
            analytic_closure=closure_dict,
            premium_readiness=readiness,
            next_research_leads=next_research_leads,
        )
    return PremiumRefinementStatusOut(
        recommended_action="ready",
        message="Premium refinement loop is closed and no automatic blocker remains.",
        analytic_closure=closure_dict,
        premium_readiness=readiness,
        next_research_leads=next_research_leads,
    )


@router.get("/sessions/{session_id}/premium-refinement-status", response_model=PremiumRefinementStatusOut)
async def get_premium_refinement_status(
    session_id: str,
    request: Request,
) -> PremiumRefinementStatusOut:
    """Return the current non-mutating premium refinement state.

    Long premium runs need a cheap status endpoint separate from the mutating
    `/premium-refine` button. The UI can call this repeatedly to explain
    whether it is waiting for research, waiting for synthesis, ready to submit
    the next analytic-depth branch, or blocked on paid-delivery quality.
    """
    session = _owned_with_cap(session_id, request)
    if _reap_stale_running_tasks(session):
        _store.update(session)
    return _build_premium_refinement_status(session)


@router.post("/sessions/{session_id}/premium-refine", response_model=PremiumRefineOut)
async def premium_refine(
    session_id: str,
    request: Request,
    payload: PremiumRefineIn,
) -> PremiumRefineOut:
    """Advance the premium report one safe refinement step.

    This endpoint is intentionally additive orchestration. It does not replace
    `/auto-depth-leads`, `/auto-dr-status`, or `/synthesize`; it chooses the
    next deterministic step a UI can call repeatedly:

    1. wait if follow-up jobs are already running;
    2. submit priority analytic-depth leads if closure is still open;
    3. resynthesize once new follow-up reports exist;
    4. otherwise return the current premium readiness state.
    """

    session = _owned_with_cap(session_id, request)
    if session.analysis is None:
        raise HTTPException(
            status_code=400,
            detail="premium-refine requires a completed /analyze first",
        )
    if _reap_stale_running_tasks(session):
        _store.update(session)

    pending_followups = _pending_followup_task_ids(session)
    if pending_followups:
        return PremiumRefineOut(
            action="wait_for_followups",
            message="Follow-up research is still running; poll /auto-dr-status before refining again.",
            pending_task_ids=pending_followups,
        )

    client_report = (
        sanitize_final_report(session.final_report)
        if session.final_report is not None
        else None
    )
    plan = build_analytic_depth_plan(
        session.raw_question,
        analysis=session.analysis,
        report=client_report,
    )
    closure = assess_analytic_closure(plan, list(session.followup_reports or []))
    open_leads = int(closure.not_started or 0) + int(closure.not_closed or 0)
    if open_leads:
        submitted = await _submit_analytic_depth_leads(
            session_id=session_id,
            session=session,
            plan=plan,
            payload=payload,
        )
        if submitted:
            return PremiumRefineOut(
                action="submitted_followups",
                message=f"Submitted {len(submitted)} analytic-depth follow-up job(s).",
                submitted_leads=submitted,
                analytic_closure=closure.model_dump(mode="json"),
            )

    running_synth = _has_running_long_task(session, "synthesize")
    if running_synth:
        return PremiumRefineOut(
            action="wait_for_followups",
            message="Synthesis is already running; poll /long-task-status before refining again.",
            pending_task_ids=[running_synth],
            analytic_closure=closure.model_dump(mode="json"),
        )

    if payload.auto_synthesize and _final_report_needs_followup_resynthesis(session):
        orch = V4Orchestrator(_store, emitter=_SessionEmitter(session_id))
        task = _start_long_task(
            session,
            phase="synthesize",
            model_preference=payload.model_preference,
            coro_factory=lambda: orch.synthesize(
                session_id,
                model_preference=payload.model_preference,
            ),
        )
        return PremiumRefineOut(
            action="synthesize_started",
            message="Started synthesis to incorporate current follow-up evidence.",
            synthesize_task=task,
            analytic_closure=closure.model_dump(mode="json"),
        )

    readiness = None
    if session.final_report is not None:
        report_for_readiness = sanitize_final_report(session.final_report)
        readiness = assess_premium_readiness(
            report_for_readiness,
            analysis=session.analysis,
            depth_plan=plan,
            closure_report=closure,
            evidence_audit=assess_evidence_support(report_for_readiness, session.analysis),
            adjudication_audit=assess_adjudication_quality(report_for_readiness, session.analysis),
        ).model_dump()
    return PremiumRefineOut(
        action="ready_or_blocked",
        message="No automatic refinement step is currently available; inspect readiness blockers.",
        analytic_closure=closure.model_dump(mode="json"),
        premium_readiness=readiness,
    )


@router.get("/sessions/{session_id}/final-report")
async def get_final_report(session_id: str, request: Request) -> dict:
    """Return only the final report and current cost, not full session JSON.

    Full V4Session payloads include source_reports/followup_reports content.
    On production Deep Research runs those markdown bodies can be large enough
    that fetching the entire session after synthesize makes the UI look stuck
    even though the final_report has already been persisted.
    """
    session = _get_owned(session_id, request)
    if session.final_report is None:
        raise HTTPException(
            status_code=409,
            detail=f"session {session_id} has no final_report yet",
        )
    return {
        "final_report": session.final_report.model_dump(mode="json"),
        "total_cost_rub": session.total_cost_rub,
        "status": session.status,
    }


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


_EXPORT_FORMATS = {
    "md", "json", "docx", "premium-docx", "premium-pptx", "pptx", "onepager",
    "premium-package", "premium-client-package",
    "next-research-brief",
    "data-pack", "sources-csv", "facts-csv", "audit-json",
    "gamma-pptx", "gamma-pdf",
    "gamma-pptx-real",  # served from disk after export-gamma-pptx finishes
}


@router.get("/sessions/{session_id}/export")
async def export_session(
    session_id: str,
    request: Request,
    format: str = "md",
    allow_draft: bool = False,
    visual_review_approved: bool = False,
) -> FileResponse:
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
    client_report = sanitize_final_report(session.final_report)
    readiness = assess_client_readiness(
        session.final_report,
        client_report=client_report,
        analysis=session.analysis,
    )

    if format == "data-pack":
        out_path = _write_data_pack(out_dir / "data_pack.zip", session, client_report)
        return FileResponse(str(out_path), media_type="application/zip", filename="data_pack.zip")

    if format == "sources-csv":
        out_path = _write_sources_csv(out_dir / "sources.csv", client_report)
        return FileResponse(str(out_path), media_type="text/csv; charset=utf-8", filename="sources.csv")

    if format == "facts-csv":
        out_path = _write_facts_csv(out_dir / "facts.csv", session)
        return FileResponse(str(out_path), media_type="text/csv; charset=utf-8", filename="facts.csv")

    if format == "audit-json":
        out_path = _write_audit_json(out_dir / "audit.json", session)
        return FileResponse(str(out_path), media_type="application/json", filename="audit.json")

    if format == "next-research-brief":
        out_path = _write_next_research_brief_file(
            out_dir / "next_research_brief.md",
            session,
            client_report,
        )
        return FileResponse(
            str(out_path),
            media_type="text/markdown; charset=utf-8",
            filename="next_research_brief.md",
        )

    # Real Gamma-generated PPTX is produced by the async export-gamma-pptx
    # endpoint (1-3 min generation). The /export route only serves the
    # already-downloaded file; if missing, point the caller at the async
    # endpoint instead of trying to render synchronously.
    if format == "gamma-pptx-real":
        out_path = out_dir / "gamma_report.pptx"
        if not out_path.exists():
            raise HTTPException(
                status_code=404,
                detail=(
                    "Gamma PPTX not generated yet for this session — "
                    "POST /sessions/{id}/export-gamma-pptx first and poll "
                    "/long-task-status until completed"
                ),
            )
        return FileResponse(
            str(out_path),
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            filename="gamma_report.pptx",
        )

    if format == "premium-client-package":
        out_path = _write_premium_package(
            out_dir / "premium_client_delivery_package.zip",
            session,
            client_report,
            visual_review_approved=visual_review_approved,
        )
        gate = _read_premium_package_gate(out_path)
        if not gate["ready"]:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "Premium package is not ready for client delivery.",
                    "gate": gate,
                },
            )
        return FileResponse(
            str(out_path),
            media_type="application/zip",
            filename="premium_client_delivery_package.zip",
        )

    if not readiness.ready and not allow_draft:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Report is not client-ready. Use allow_draft=true to export a draft, or inspect audit-json/data-pack.",
                "readiness": readiness.model_dump(),
            },
        )

    if format == "premium-package":
        out_path = _write_premium_package(out_dir / "premium_delivery_package.zip", session, client_report)
        return FileResponse(
            str(out_path),
            media_type="application/zip",
            filename="premium_delivery_package.zip",
        )

    filename, writer, media_type = _export_handler(format)
    if format == "docx":
        # Use auto-selecting renderer (Node.js docx-js preferred, python-docx fallback)
        # — operates on the FinalReport directly, not the flattened report_dict.
        from smart_report.exporters import render_docx as _render_docx
        out_path = _render_docx(client_report, out_dir / filename)
    elif format == "premium-docx":
        from smart_report.exporters import (
            assemble_premium_report_document as _assemble_premium_report_document,
            render_premium_docx as _render_premium_docx,
        )
        depth_plan = (
            build_analytic_depth_plan(
                session.raw_question,
                analysis=session.analysis,
                report=client_report,
            )
            if session.analysis is not None
            else None
        )
        premium_readiness = assess_premium_readiness(
            client_report,
            analysis=session.analysis,
            depth_plan=depth_plan,
            closure_report=(
                assess_analytic_closure(depth_plan, list(session.followup_reports or []))
                if depth_plan is not None
                else None
            ),
            evidence_audit=assess_evidence_support(client_report, session.analysis),
            adjudication_audit=assess_adjudication_quality(client_report, session.analysis),
        ).model_dump()
        premium_document = _assemble_premium_report_document(
            client_report,
            analysis=session.analysis,
            premium_readiness=premium_readiness,
        )
        out_path = _render_premium_docx(premium_document, out_dir / filename)
    elif format == "premium-pptx":
        from smart_report.exporters import (
            assemble_premium_report_document as _assemble_premium_report_document,
            render_premium_pptx as _render_premium_pptx,
        )
        depth_plan = (
            build_analytic_depth_plan(
                session.raw_question,
                analysis=session.analysis,
                report=client_report,
            )
            if session.analysis is not None
            else None
        )
        premium_readiness = assess_premium_readiness(
            client_report,
            analysis=session.analysis,
            depth_plan=depth_plan,
            closure_report=(
                assess_analytic_closure(depth_plan, list(session.followup_reports or []))
                if depth_plan is not None
                else None
            ),
            evidence_audit=assess_evidence_support(client_report, session.analysis),
            adjudication_audit=assess_adjudication_quality(client_report, session.analysis),
        ).model_dump()
        premium_document = _assemble_premium_report_document(
            client_report,
            analysis=session.analysis,
            premium_readiness=premium_readiness,
        )
        out_path = _render_premium_pptx(premium_document, out_dir / filename)
    else:
        report_dict = v4_to_report_dict(client_report)
        out_path = writer(out_dir / filename, report_dict)
    return FileResponse(
        str(out_path),
        media_type=media_type,
        filename=filename,
    )


@router.post(
    "/sessions/{session_id}/export-gamma-pptx",
    response_model=LongTaskOut,
    status_code=202,
)
async def export_gamma_pptx(
    session_id: str, request: Request
) -> LongTaskOut:
    """Submit a Gamma-API PPTX generation as a background task.

    Returns 202 + task_id within <1s. Gamma generates the deck in 1-3
    minutes; the task downloads the result to runs_dir/v4_{sid}/
    gamma_report.pptx. Clients then call GET /export?format=gamma-pptx-real
    to download the file.

    Requires GAMMA_API_KEY in env. If unset, the task fails with a
    clear error in the long-task-status response.
    """
    session = _get_owned(session_id, request)
    if session.final_report is None:
        raise HTTPException(
            status_code=409,
            detail="no final_report on session — run /synthesize first",
        )

    out_dir = _session_artefact_dir(session_id)
    dest = out_dir / "gamma_report.pptx"
    final_report = sanitize_final_report(session.final_report)

    from ..exporters.gamma_pptx import generate_pptx as _generate_pptx

    return _start_long_task(
        session,
        phase="export-pptx",
        model_preference=None,
        coro_factory=lambda: _generate_pptx(final_report, dest),
    )


def _write_data_pack(path: Path, session: V4Session, client_report: FinalReport) -> Path:
    """Write a full data room ZIP for the session."""

    path.parent.mkdir(parents=True, exist_ok=True)
    raw_report = session.final_report
    depth_plan = (
        build_analytic_depth_plan(
            session.raw_question,
            analysis=session.analysis,
            report=client_report,
        )
        if session.analysis
        else None
    )
    analytic_closure = (
        assess_analytic_closure(depth_plan, list(session.followup_reports or []))
        if depth_plan
        else None
    )
    evidence_audit = assess_evidence_support(client_report, session.analysis)
    adjudication_audit = assess_adjudication_quality(client_report, session.analysis)
    premium_readiness = assess_premium_readiness(
        client_report,
        analysis=session.analysis,
        depth_plan=depth_plan,
        closure_report=analytic_closure,
        evidence_audit=evidence_audit,
        adjudication_audit=adjudication_audit,
    ).model_dump()
    payload = {
        "session": session.model_dump(mode="json", exclude={"source_reports", "followup_reports"}),
        "client_report": client_report.model_dump(mode="json"),
        "raw_final_report": raw_report.model_dump(mode="json") if raw_report else None,
        "analytic_depth": depth_plan.model_dump(mode="json") if depth_plan else None,
        "analytic_closure": analytic_closure.model_dump(mode="json") if analytic_closure else None,
        "evidence_audit": evidence_audit.model_dump(mode="json"),
        "adjudication_audit": adjudication_audit.model_dump(mode="json"),
        "client_leaks": contains_client_leak(client_report),
        "client_readiness": assess_client_readiness(
            raw_report or client_report,
            client_report=client_report,
            analysis=session.analysis,
        ).model_dump(),
        "premium_readiness": premium_readiness,
    }
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "manifest.json",
            json.dumps(
                {
                    "session_id": session.session_id,
                    "status": session.status,
                    "created_at": session.created_at.isoformat(),
                    "total_cost_rub": session.total_cost_rub,
                    "files": [
                        "session.json",
                        "client_report.json",
                        "raw_final_report.json",
                        "analytic_depth.json",
                        "analytic_closure.json",
                        "evidence_audit.json",
                        "adjudication_audit.json",
                        "analysis.json",
                        "research_prompt.json",
                        "events.json",
                        "client_leaks.json",
                        "client_readiness.json",
                        "premium_readiness.json",
                        "sources.csv",
                        "facts.csv",
                        "source_reports/",
                        "followup_reports/",
                    ],
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
        )
        zf.writestr("session.json", json.dumps(payload["session"], ensure_ascii=False, indent=2, default=str))
        zf.writestr("client_report.json", json.dumps(payload["client_report"], ensure_ascii=False, indent=2, default=str))
        zf.writestr("raw_final_report.json", json.dumps(payload["raw_final_report"], ensure_ascii=False, indent=2, default=str))
        zf.writestr(
            "analytic_depth.json",
            json.dumps(payload["analytic_depth"], ensure_ascii=False, indent=2, default=str),
        )
        zf.writestr(
            "analytic_closure.json",
            json.dumps(payload["analytic_closure"], ensure_ascii=False, indent=2, default=str),
        )
        zf.writestr(
            "evidence_audit.json",
            json.dumps(payload["evidence_audit"], ensure_ascii=False, indent=2, default=str),
        )
        zf.writestr(
            "adjudication_audit.json",
            json.dumps(payload["adjudication_audit"], ensure_ascii=False, indent=2, default=str),
        )
        zf.writestr(
            "analysis.json",
            json.dumps(session.analysis.model_dump(mode="json") if session.analysis else None, ensure_ascii=False, indent=2, default=str),
        )
        zf.writestr(
            "research_prompt.json",
            json.dumps(session.research_prompt.model_dump(mode="json") if session.research_prompt else None, ensure_ascii=False, indent=2, default=str),
        )
        zf.writestr(
            "events.json",
            json.dumps(_V4_EVENTS.get(session.session_id, []), ensure_ascii=False, indent=2, default=str),
        )
        zf.writestr(
            "client_leaks.json",
            json.dumps(payload["client_leaks"], ensure_ascii=False, indent=2, default=str),
        )
        zf.writestr(
            "client_readiness.json",
            json.dumps(payload["client_readiness"], ensure_ascii=False, indent=2, default=str),
        )
        zf.writestr(
            "premium_readiness.json",
            json.dumps(payload["premium_readiness"], ensure_ascii=False, indent=2, default=str),
        )
        zf.writestr("sources.csv", _sources_csv_text(client_report))
        zf.writestr("facts.csv", _facts_csv_text(session))
        for idx, upload in enumerate(session.source_reports, start=1):
            zf.writestr(f"source_reports/{idx:02d}_{_safe_zip_name(upload.filename)}", upload.content)
        for idx, upload in enumerate(session.followup_reports, start=1):
            zf.writestr(f"followup_reports/{idx:02d}_{_safe_zip_name(upload.filename)}", upload.content)
    return path


def _write_premium_package(
    path: Path,
    session: V4Session,
    client_report: FinalReport,
    *,
    visual_review_approved: bool = False,
) -> Path:
    """Write a client-facing premium delivery bundle.

    Unlike ``data-pack`` this package is organized around delivery artifacts:
    the long-form report, the executive deck, readiness/audit files, and a
    nested technical data pack for traceability.
    """

    from smart_report.exporters import (
        assemble_premium_report_document as _assemble_premium_report_document,
        render_premium_docx as _render_premium_docx,
        render_premium_pptx as _render_premium_pptx,
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    depth_plan = (
        build_analytic_depth_plan(
            session.raw_question,
            analysis=session.analysis,
            report=client_report,
        )
        if session.analysis
        else None
    )
    analytic_closure = (
        assess_analytic_closure(depth_plan, list(session.followup_reports or []))
        if depth_plan
        else None
    )
    evidence_audit = assess_evidence_support(client_report, session.analysis)
    adjudication_audit = assess_adjudication_quality(client_report, session.analysis)
    premium_readiness = assess_premium_readiness(
        client_report,
        analysis=session.analysis,
        depth_plan=depth_plan,
        closure_report=analytic_closure,
        evidence_audit=evidence_audit,
        adjudication_audit=adjudication_audit,
    ).model_dump()
    client_readiness = assess_client_readiness(
        session.final_report,
        client_report=client_report,
        analysis=session.analysis,
    ).model_dump()
    premium_document = _assemble_premium_report_document(
        client_report,
        analysis=session.analysis,
        premium_readiness=premium_readiness,
    )
    report_path = _render_premium_docx(premium_document, path.parent / "premium_report.docx")
    deck_path = _render_premium_pptx(premium_document, path.parent / "premium_deck.pptx")
    data_pack_path = _write_data_pack(path.parent / "data_pack.zip", session, client_report)
    artifact_qa = _premium_artifact_qa(report_path, deck_path, path.parent / "artifact_qa")
    visual_review = build_visual_review_gate(artifact_qa, approved=visual_review_approved)
    audit_path = _write_audit_json(path.parent / "audit.json", session, visual_review=visual_review)
    artifact_summary = _artifact_qa_manifest_summary(artifact_qa)

    manifest = {
        "package_type": "smart_report_premium_delivery",
        "session_id": session.session_id,
        "status": session.status,
        "ready_for_client_delivery": bool(client_readiness.get("ready")),
        "ready_for_paid_premium_delivery": bool(premium_readiness.get("ready")),
        "premium_score": premium_readiness.get("score"),
        "artifact_qa_status": artifact_qa.get("status"),
        "docx_pages": artifact_summary.get("docx_pages"),
        "docx_pages_source": artifact_summary.get("docx_pages_source"),
        "deck_slides": artifact_summary.get("deck_slides"),
        "visual_review_status": visual_review.status,
        "analytic_closure_score": (
            analytic_closure.overall_score if analytic_closure is not None else None
        ),
        "open_analytic_leads": (
            int(analytic_closure.not_started or 0) + int(analytic_closure.not_closed or 0)
            if analytic_closure is not None
            else None
        ),
        "unsupported_conclusions": int(evidence_audit.unsupported or 0),
        "unresolved_conflicts": int(adjudication_audit.unresolved or 0),
        "critical_unresolved_conflicts": int(adjudication_audit.critical_unresolved or 0),
        "files": [
            "01_premium_report.docx",
            "02_premium_deck.pptx",
            "03_premium_readiness.json",
            "04_client_readiness.json",
            "05_audit.json",
            "06_analytic_closure.json",
            "07_artifact_qa.json",
            "07_artifact_qa/",
            "08_sources.csv",
            "09_facts.csv",
            "10_data_pack.zip",
            "11_evidence_audit.json",
            "12_adjudication_audit.json",
            "13_visual_review.json",
            "14_next_research_brief.md",
        ],
    }
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("00_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2, default=str))
        zf.write(report_path, "01_premium_report.docx")
        zf.write(deck_path, "02_premium_deck.pptx")
        zf.writestr(
            "03_premium_readiness.json",
            json.dumps(premium_readiness, ensure_ascii=False, indent=2, default=str),
        )
        zf.writestr(
            "04_client_readiness.json",
            json.dumps(client_readiness, ensure_ascii=False, indent=2, default=str),
        )
        zf.write(audit_path, "05_audit.json")
        zf.writestr(
            "06_analytic_closure.json",
            json.dumps(
                analytic_closure.model_dump(mode="json") if analytic_closure else None,
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
        )
        zf.writestr(
            "07_artifact_qa.json",
            json.dumps(artifact_qa, ensure_ascii=False, indent=2, default=str),
        )
        _write_artifact_qa_bundle(zf, artifact_qa, path.parent / "artifact_qa")
        zf.writestr("08_sources.csv", _sources_csv_text(client_report))
        zf.writestr("09_facts.csv", _facts_csv_text(session))
        zf.write(data_pack_path, "10_data_pack.zip")
        zf.writestr(
            "11_evidence_audit.json",
            json.dumps(evidence_audit.model_dump(mode="json"), ensure_ascii=False, indent=2, default=str),
        )
        zf.writestr(
            "12_adjudication_audit.json",
            json.dumps(adjudication_audit.model_dump(mode="json"), ensure_ascii=False, indent=2, default=str),
        )
        zf.writestr(
            "13_visual_review.json",
            json.dumps(visual_review.model_dump(mode="json"), ensure_ascii=False, indent=2, default=str),
        )
        zf.writestr(
            "14_next_research_brief.md",
            _next_research_brief_markdown(depth_plan, analytic_closure),
        )
    return path


def _write_next_research_brief_file(
    path: Path,
    session: V4Session,
    client_report: FinalReport | None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    depth_plan = (
        build_analytic_depth_plan(
            session.raw_question,
            analysis=session.analysis,
            report=client_report,
        )
        if session.analysis
        else None
    )
    analytic_closure = (
        assess_analytic_closure(depth_plan, list(session.followup_reports or []))
        if depth_plan
        else None
    )
    path.write_text(
        _next_research_brief_markdown(depth_plan, analytic_closure),
        encoding="utf-8",
    )
    return path


def _read_premium_package_gate(path: Path) -> dict:
    with zipfile.ZipFile(path) as zf:
        manifest = json.loads(zf.read("00_manifest.json").decode("utf-8"))
        premium_readiness = json.loads(zf.read("03_premium_readiness.json").decode("utf-8"))
        client_readiness = json.loads(zf.read("04_client_readiness.json").decode("utf-8"))
        artifact_qa = json.loads(zf.read("07_artifact_qa.json").decode("utf-8"))
        analytic_closure = json.loads(zf.read("06_analytic_closure.json").decode("utf-8"))
        evidence_audit = json.loads(zf.read("11_evidence_audit.json").decode("utf-8"))
        adjudication_audit = json.loads(zf.read("12_adjudication_audit.json").decode("utf-8"))
        visual_review = json.loads(zf.read("13_visual_review.json").decode("utf-8"))
    blockers = []
    if not client_readiness.get("ready"):
        blockers.append("client_readiness_not_ready")
    if not premium_readiness.get("ready"):
        blockers.append("premium_readiness_not_ready")
    if artifact_qa.get("status") != "passed":
        blockers.append("artifact_qa_not_passed")
    docx_pages = _artifact_qa_docx_page_count(artifact_qa)
    if docx_pages is not None and docx_pages < 20:
        blockers.append("premium_report_below_20_pages")
    if analytic_closure and int(analytic_closure.get("not_started") or 0) + int(analytic_closure.get("not_closed") or 0) > 0:
        blockers.append("analytic_closure_open_leads")
    if evidence_audit and int(evidence_audit.get("unsupported") or 0) > 0:
        blockers.append("evidence_audit_unsupported_conclusions")
    if adjudication_audit and int(adjudication_audit.get("critical_unresolved") or 0) > 0:
        blockers.append("adjudication_audit_critical_unresolved")
    elif adjudication_audit and int(adjudication_audit.get("unresolved") or 0) > 0:
        blockers.append("adjudication_audit_unresolved_conflicts")
    if not visual_review.get("ready"):
        blockers.append("visual_review_not_approved")
    return {
        "ready": not blockers,
        "blockers": blockers,
        "manifest": manifest,
        "client_readiness": client_readiness,
        "premium_readiness": premium_readiness,
        "artifact_qa": artifact_qa,
        "analytic_closure": analytic_closure,
        "evidence_audit": evidence_audit,
        "adjudication_audit": adjudication_audit,
        "visual_review": visual_review,
    }


def _artifact_qa_docx_page_count(artifact_qa: dict) -> int | None:
    for result in artifact_qa.get("results") or []:
        if result.get("kind") != "docx":
            continue
        metrics = result.get("metrics") or {}
        pages = metrics.get("rendered_pages")
        if pages is None:
            pages = metrics.get("estimated_pages")
        if pages is None:
            return None
        try:
            return int(pages)
        except (TypeError, ValueError):
            return None
    return None


def _artifact_qa_manifest_summary(artifact_qa: dict) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "docx_pages": None,
        "docx_pages_source": None,
        "deck_slides": None,
    }
    for result in artifact_qa.get("results") or []:
        metrics = result.get("metrics") or {}
        if result.get("kind") == "docx":
            rendered_pages = metrics.get("rendered_pages")
            estimated_pages = metrics.get("estimated_pages")
            if rendered_pages is not None:
                summary["docx_pages"] = rendered_pages
                summary["docx_pages_source"] = "rendered_pages"
            elif estimated_pages is not None:
                summary["docx_pages"] = estimated_pages
                summary["docx_pages_source"] = "estimated_pages"
        elif result.get("kind") == "pptx":
            summary["deck_slides"] = metrics.get("rendered_slides") or metrics.get("slides")
    return summary


def _premium_artifact_qa(report_path: Path, deck_path: Path, out_dir: Path) -> dict:
    try:
        from scripts.premium_artifact_qa import run_qa

        return run_qa(
            docx_path=report_path,
            pptx_path=deck_path,
            out_dir=out_dir,
            render=True,
        )
    except Exception as exc:  # pragma: no cover - defensive export path
        return {
            "status": "failed",
            "summary": {"artifacts": 2, "issues": 1},
            "results": [],
            "error": f"Premium artifact QA failed to run: {exc}",
        }


def _write_artifact_qa_bundle(zf: zipfile.ZipFile, artifact_qa: dict, out_dir: Path) -> None:
    render_index = artifact_qa.get("render_index")
    if render_index:
        index_path = Path(str(render_index))
        if index_path.exists():
            zf.write(index_path, "07_artifact_qa/index.html")
    for result in artifact_qa.get("results") or []:
        for rendered_file in result.get("rendered_files") or []:
            rendered_path = Path(str(rendered_file))
            if rendered_path.suffix.lower() != ".png" or not rendered_path.exists():
                continue
            try:
                rel = rendered_path.relative_to(out_dir)
            except ValueError:
                rel = Path(rendered_path.name)
            zf.write(rendered_path, str(Path("07_artifact_qa") / rel))


def _next_research_brief_markdown(
    depth_plan: Any,
    analytic_closure: Any,
) -> str:
    if depth_plan is None:
        return "# Next Research Brief\n\nNo analytic-depth plan was generated for this package.\n"

    closure_by_id = {}
    if analytic_closure is not None:
        closure_by_id = {
            item.lead_id: item
            for item in getattr(analytic_closure, "lead_closures", []) or []
        }

    lines = [
        "# Next Research Brief",
        "",
        "This brief is generated from the analytic-depth layer. It lists the research branches that must be closed before the package should be treated as paid-client-ready.",
        "",
        f"Question: {depth_plan.question}",
        f"Domain hint: {depth_plan.domain_hint}",
        "",
        "## Priority Leads",
        "",
    ]
    leads = [
        lead
        for lead in depth_plan.research_leads
        if lead.priority in {"must", "should"}
    ]
    if not leads:
        lines.append("No must/should research leads were generated.")
    for lead in leads:
        closure = closure_by_id.get(lead.id)
        status = getattr(closure, "status", "not_assessed")
        lines.extend(
            [
                f"### {lead.id}: {lead.kind} / {lead.priority}",
                "",
                f"Status: {status}",
                f"Recommended service: {lead.recommended_service}"
                + (f" ({lead.recommended_mode})" if lead.recommended_mode else ""),
                "",
                "**Prompt**",
                "",
                lead.prompt,
                "",
                "**Why this matters**",
                "",
                lead.rationale or "No rationale provided.",
                "",
                "**Targets**",
                "",
                "- Entities: " + (", ".join(lead.target_entities) if lead.target_entities else "not specified"),
                "- Metrics: " + (", ".join(lead.target_metrics) if lead.target_metrics else "not specified"),
                "- Candidate sources: "
                + (", ".join(lead.candidate_sources) if lead.candidate_sources else "not specified"),
                "",
            ]
        )
        if closure is not None and getattr(closure, "missing_signals", None):
            lines.extend(
                [
                    "**Missing closure signals**",
                    "",
                    *[f"- {item}" for item in closure.missing_signals],
                    "",
                ]
            )

    lines.extend(
        [
            "## Benchmarks To Add",
            "",
            *[f"- {item}" for item in depth_plan.benchmark_questions],
            "",
            "## Monitoring Indicators",
            "",
            *[f"- {item}" for item in depth_plan.monitoring_indicators],
            "",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def _write_sources_csv(path: Path, report: FinalReport) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_sources_csv_text(report), encoding="utf-8-sig")
    return path


def _write_facts_csv(path: Path, session: V4Session) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_facts_csv_text(session), encoding="utf-8-sig")
    return path


def _write_audit_json(path: Path, session: V4Session, *, visual_review=None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    client_report = sanitize_final_report(session.final_report) if session.final_report else None
    depth_plan = (
        build_analytic_depth_plan(
            session.raw_question,
            analysis=session.analysis,
            report=client_report,
        )
        if session.analysis
        else None
    )
    analytic_closure = (
        assess_analytic_closure(depth_plan, list(session.followup_reports or []))
        if depth_plan is not None
        else None
    )
    evidence_audit = assess_evidence_support(client_report, session.analysis) if client_report else None
    adjudication_audit = assess_adjudication_quality(client_report, session.analysis) if client_report else None
    audit = {
        "session_id": session.session_id,
        "status": session.status,
        "total_cost_rub": session.total_cost_rub,
        "client_readiness": (
            assess_client_readiness(
                session.final_report,
                client_report=client_report,
                analysis=session.analysis,
            ).model_dump()
            if session.final_report
            else None
        ),
        "premium_readiness": (
            assess_premium_readiness(
                client_report,
                analysis=session.analysis,
                depth_plan=depth_plan,
                closure_report=analytic_closure,
                evidence_audit=evidence_audit,
                adjudication_audit=adjudication_audit,
            ).model_dump()
            if client_report
            else None
        ),
        "analytic_depth": depth_plan.model_dump(mode="json") if depth_plan else None,
        "analytic_closure": analytic_closure.model_dump(mode="json") if analytic_closure else None,
        "evidence_audit": evidence_audit.model_dump(mode="json") if evidence_audit else None,
        "adjudication_audit": adjudication_audit.model_dump(mode="json") if adjudication_audit else None,
        "visual_review": visual_review.model_dump(mode="json") if visual_review else None,
        "analysis": session.analysis.model_dump(mode="json") if session.analysis else None,
        "normalized_reports": [n.model_dump(mode="json") for n in session.normalized_reports],
        "pending_long_tasks": session.pending_long_tasks,
        "raw_final_report": session.final_report.model_dump(mode="json") if session.final_report else None,
    }
    path.write_text(json.dumps(audit, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path


def _sources_csv_text(report: FinalReport) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["number", "title", "url", "tool", "reliability", "publisher", "date"])
    seen: set[str] = set()
    for source in report.bibliography:
        ref = source.source_ref
        seen.add(ref.url)
        writer.writerow([
            source.number,
            ref.title or "",
            ref.url,
            ref.accessed_via,
            ref.confidence,
            ref.publisher or "",
            ref.date or "",
        ])
    next_number = len(seen) + 1
    for source in report.all_sources:
        if source.url in seen:
            continue
        writer.writerow([next_number, source.title, source.url, source.tool, source.reliability, "", ""])
        next_number += 1
    return out.getvalue()


def _facts_csv_text(session: V4Session) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["fact_id", "value", "metric", "subject", "timeframe", "relevance", "category", "sources"])
    facts = []
    if session.analysis:
        facts = session.analysis.high_relevance_facts or session.analysis.all_numeric_facts
    for fact in facts:
        writer.writerow([
            fact.fact_id,
            fact.value,
            fact.metric,
            fact.subject,
            fact.timeframe or "",
            fact.relevance_to_question,
            fact.fact_category,
            " | ".join(src.url for src in fact.sources if src.url),
        ])
    return out.getvalue()


def _safe_zip_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9А-Яа-я._ -]+", "_", name or "upload.md").strip()
    return cleaned or "upload.md"


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
    if format == "premium-docx":
        return (
            "premium_report.docx",
            write_docx,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    if format == "premium-pptx":
        return (
            "premium_deck.pptx",
            write_pptx,
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
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
    # gamma-pptx-real is served by export_session itself (file-only, no writer).
    raise HTTPException(status_code=400, detail=f"unknown format {format!r}")


# Keep MIME registry consistent on Windows where .md mimetypes return None.
mimetypes.add_type("text/markdown", ".md")
