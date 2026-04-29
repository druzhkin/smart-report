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
import concurrent.futures as _cf
import threading as _threading

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
    # submit_async_research does not touch pending_dr_jobs — endpoint adds
    # the entry, tagged is_followup so auto_dr_status routes to followup_reports.
    session.pending_dr_jobs = list(session.pending_dr_jobs or []) + [{
        "task_id": sub.task_id,
        "service": payload.service,
        "mode": payload.mode,
        "cost_usd": sub.cost_usd,
        "cost_rub": cost_rub,
        "submitted_at": time.time(),
        "state": "running",
        "is_followup": True,
    }]
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
        # result into source_reports AND removes the pending entry on
        # completion. So "not found in pending" + "matching source_report
        # exists" = silently completed. Surface as state=completed so the
        # frontend shows success instead of "task lost".
        prefix = task_id[:8]
        for svc_guess in ("openai", "perplexity"):
            for u in (session.source_reports or []):
                if u.filename in (
                    f"auto_dr_{svc_guess}_{prefix}.md",
                    f"auto_dr_{svc_guess}_{prefix}_partial.md",
                ):
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
    "md", "json", "docx", "pptx", "onepager",
    "gamma-pptx", "gamma-pdf",
    "gamma-pptx-real",  # served from disk after export-gamma-pptx finishes
}


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
    final_report = session.final_report

    from ..exporters.gamma_pptx import generate_pptx as _generate_pptx

    return _start_long_task(
        session,
        phase="export-pptx",
        model_preference=None,
        coro_factory=lambda: _generate_pptx(final_report, dest),
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
    # gamma-pptx-real is served by export_session itself (file-only, no writer).
    raise HTTPException(status_code=400, detail=f"unknown format {format!r}")


# Keep MIME registry consistent on Windows where .md mimetypes return None.
mimetypes.add_type("text/markdown", ".md")
