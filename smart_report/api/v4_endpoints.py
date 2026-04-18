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
import time
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..events import ALLOWED_PHASES, EventEmitter
from ..models import ResearchPrompt, V4Session
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


# ---- endpoints ----


@router.post("/sessions", response_model=CreateSessionOut)
async def create_session(payload: CreateSessionIn) -> CreateSessionOut:
    session_id = uuid.uuid4().hex[:12]
    _store.create(session_id=session_id, raw_question=payload.question)
    _V4_EVENTS[session_id] = []
    _V4_EVENT_SIGNALS[session_id] = asyncio.Event()
    log.info("v4 session %s created", session_id)
    return CreateSessionOut(session_id=session_id)


@router.post("/sessions/{session_id}/generate-prompt", response_model=ResearchPrompt)
async def generate_prompt(session_id: str) -> ResearchPrompt:
    if not _store.exists(session_id):
        raise HTTPException(status_code=404, detail=f"session {session_id} not found")
    orch = V4Orchestrator(_store, emitter=_SessionEmitter(session_id))
    try:
        return await orch.generate_prompt(session_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        log.exception("v4 generate_prompt failed for %s", session_id)
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}") from e


# ---- Track B stubs --------------------------------------------------------
# Registered so the route table is stable for the frontend / tests. Each stub
# returns 501. Track B replaces the body in-place; no wiring changes needed.


@router.post("/sessions/{session_id}/upload-reports")
async def upload_reports(session_id: str) -> dict:
    # TRACK B: fill body — accept list[UploadFile], persist UploadedMarkdown[], return them.
    raise HTTPException(status_code=501, detail="Track B: upload-reports not yet implemented")


@router.post("/sessions/{session_id}/analyze")
async def analyze(session_id: str) -> dict:
    # TRACK B: fill body — call V4Orchestrator.analyze(), return AnalysisOutput.
    raise HTTPException(status_code=501, detail="Track B: analyze not yet implemented")


@router.post("/sessions/{session_id}/upload-followup")
async def upload_followup(session_id: str) -> dict:
    # TRACK B: fill body — accept list[UploadFile] followup reports, persist UploadedMarkdown[].
    raise HTTPException(status_code=501, detail="Track B: upload-followup not yet implemented")


@router.post("/sessions/{session_id}/synthesize")
async def synthesize(session_id: str) -> dict:
    # TRACK B: fill body — call V4Orchestrator.synthesize(), return FinalReport.
    raise HTTPException(status_code=501, detail="Track B: synthesize not yet implemented")


@router.get("/sessions/{session_id}")
async def get_session(session_id: str) -> dict:
    # TRACK B: fill body — return V4Session.model_dump() (plus synthesised fields if desired).
    # Minimal passthrough kept here so Track C has something to smoke-test generate_prompt against.
    if not _store.exists(session_id):
        raise HTTPException(status_code=404, detail=f"session {session_id} not found")
    s = _store.get(session_id)
    return s.model_dump(mode="json")


@router.get("/sessions/{session_id}/events")
async def get_events(session_id: str, since: int = 0, timeout: float = 25.0) -> dict:
    # TRACK B: enrich with status/error/cursor parity against v3 /events.
    # Track A ships a working long-poll so the frontend pipeline view can hook up early.
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


@router.get("/sessions/{session_id}/export")
async def export_session(session_id: str, format: str = "md") -> dict:
    # TRACK B: fill body — route through exporters/v4_to_report.py adapter then reuse v3 exporters.
    raise HTTPException(status_code=501, detail="Track B: export not yet implemented")
