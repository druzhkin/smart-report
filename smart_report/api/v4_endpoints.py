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
import re
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

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
from ..models import (
    AnalysisOutput,
    DetectedTool,
    FinalReport,
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


# ---- Track B endpoints ----------------------------------------------------


@router.post("/sessions/{session_id}/upload-reports")
async def upload_reports(
    session_id: str, files: list[UploadFile]
) -> list[dict[str, Any]]:
    return await _upload_markdown(session_id, files, dest="source")


@router.post("/sessions/{session_id}/upload-followup")
async def upload_followup(
    session_id: str, files: list[UploadFile]
) -> list[dict[str, Any]]:
    return await _upload_markdown(session_id, files, dest="followup")


@router.post("/sessions/{session_id}/analyze", response_model=AnalysisOutput)
async def analyze(session_id: str) -> AnalysisOutput:
    if not _store.exists(session_id):
        raise HTTPException(status_code=404, detail=f"session {session_id} not found")
    orch = V4Orchestrator(_store, emitter=_SessionEmitter(session_id))
    try:
        return await orch.analyze(session_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        log.exception("v4 analyze failed for %s", session_id)
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}") from e


@router.post("/sessions/{session_id}/synthesize", response_model=FinalReport)
async def synthesize(session_id: str) -> FinalReport:
    if not _store.exists(session_id):
        raise HTTPException(status_code=404, detail=f"session {session_id} not found")
    orch = V4Orchestrator(_store, emitter=_SessionEmitter(session_id))
    try:
        return await orch.synthesize(session_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        log.exception("v4 synthesize failed for %s", session_id)
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}") from e


@router.get("/sessions/{session_id}")
async def get_session(session_id: str) -> dict:
    if not _store.exists(session_id):
        raise HTTPException(status_code=404, detail=f"session {session_id} not found")
    s = _store.get(session_id)
    return s.model_dump(mode="json")


@router.get("/sessions/{session_id}/events")
async def get_events(session_id: str, since: int = 0, timeout: float = 25.0) -> dict:
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
async def export_session(session_id: str, format: str = "md") -> FileResponse:
    if format not in _EXPORT_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"unknown format {format!r}; allowed: {sorted(_EXPORT_FORMATS)}",
        )
    if not _store.exists(session_id):
        raise HTTPException(status_code=404, detail=f"session {session_id} not found")
    session = _store.get(session_id)
    if session.final_report is None:
        raise HTTPException(
            status_code=409,
            detail=f"session {session_id} has no final_report yet; call /synthesize first",
        )

    report_dict = v4_to_report_dict(session.final_report)
    out_dir = _session_artefact_dir(session_id)
    filename, writer, media_type = _export_handler(format)
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
