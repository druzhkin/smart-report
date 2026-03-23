import asyncio
import json
import os
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from loguru import logger
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from backend.config import normalize_database_url, settings
from backend.pricing import get_public_pricing
from backend.schemas.intake import UserRequest
from backend.schemas.report_schema import ReportOutput, ReportStatus
from backend.utils.push import save_push_subscription

router = APIRouter()

DEPTH_ESTIMATED_MINUTES: dict[str, int] = {
    "light": 3,
    "standard": 8,
    "deep": 15,
    "exhaustive": 30,
}

STEP_LABELS: dict[str, str] = {
    "intake": "Intake & Analysis",
    "cost_guard": "Cost Guard",
    "prompt_router": "Prompt Router",
    "prompt_king": "Prompt Optimization",
    "prompt_splitter": "Prompt Splitting",
    "supervisor": "Supervisor",
    "research": "Research",
    "summarization": "Summarization",
    "reflect": "Reflection",
    "citation_verifier": "Citation Verification",
    "research_critique": "Research Critique",
    "viz_agent": "Visualization",
    "render_and_present": "Rendering",
    "qa": "Quality Assurance",
    "save_to_knowledge_library": "Saving to Library",
}


class CreateReportRequest(BaseModel):
    request: str
    depth: str = "standard"
    output_formats: list[str] = ["pdf", "docx"]


class FeedbackRequest(BaseModel):
    rating: int
    comment: str = ""


class PushSubscriptionKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscriptionRequest(BaseModel):
    endpoint: str
    keys: PushSubscriptionKeys


class SessionMeta(BaseModel):
    session_id: str
    request: str
    depth: str
    output_formats: list[str]
    status: str = "pending"
    cost_usd: float = 0.0
    tokens_used: int = 0
    report_urls: dict[str, str] = {}
    created_at: datetime
    report: ReportOutput | None = None
    feedback: dict | None = None
    verdict: str | None = None

    model_config = {"arbitrary_types_allowed": True}


class ReportSummary(BaseModel):
    session_id: str
    title: str
    status: str
    created_at: datetime
    cost_usd: float = 0.0
    verdict: str | None = None
    output_formats: list[str] = []


_sessions: dict[str, SessionMeta] = {}
_session_events: dict[str, list[dict]] = {}
_session_queues: dict[str, asyncio.Queue] = {}

_CREATE_REPORTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS reports (
    session_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    cost_usd REAL DEFAULT 0.0,
    verdict TEXT DEFAULT NULL,
    output_formats TEXT DEFAULT '[]'
)
"""


def _db_url() -> str:
    return normalize_database_url(settings.postgres_url, async_driver=True)


async def _ensure_reports_table() -> None:
    engine = create_async_engine(_db_url(), future=True)
    try:
        async with engine.begin() as conn:
            await conn.execute(text(_CREATE_REPORTS_TABLE_SQL))
    finally:
        await engine.dispose()


async def _upsert_report_summary(session: SessionMeta) -> None:
    try:
        engine = create_async_engine(_db_url(), future=True)
        try:
            async with engine.begin() as conn:
                await conn.execute(text(_CREATE_REPORTS_TABLE_SQL))
                await conn.execute(
                    text(
                        """
                        INSERT INTO reports (
                            session_id, title, status, created_at, cost_usd, verdict, output_formats
                        )
                        VALUES (
                            :session_id, :title, :status, :created_at, :cost_usd, :verdict, :output_formats
                        )
                        ON CONFLICT(session_id) DO UPDATE SET
                            title = excluded.title,
                            status = excluded.status,
                            cost_usd = excluded.cost_usd,
                            verdict = excluded.verdict,
                            output_formats = excluded.output_formats
                        """
                    ),
                    {
                        "session_id": session.session_id,
                        "title": (session.report.title if session.report else session.request[:120]) or "Untitled report",
                        "status": session.status,
                        "created_at": session.created_at.isoformat(),
                        "cost_usd": session.cost_usd,
                        "verdict": session.verdict,
                        "output_formats": json.dumps(session.output_formats),
                    },
                )
        finally:
            await engine.dispose()
    except Exception as exc:
        logger.warning(f"DB upsert failed (reports table): {exc}")


async def _list_report_summaries() -> list[ReportSummary]:
    try:
        await _ensure_reports_table()
        engine = create_async_engine(_db_url(), future=True)
        try:
            async with engine.connect() as conn:
                result = await conn.execute(
                    text(
                        """
                        SELECT session_id, title, status, created_at, cost_usd, verdict, output_formats
                        FROM reports
                        ORDER BY created_at DESC
                        """
                    )
                )
                rows = result.mappings().all()
        finally:
            await engine.dispose()
    except Exception as exc:
        logger.warning(f"Failed to load report summaries, returning empty list: {exc}")
        return []

    return [
        ReportSummary(
            session_id=row["session_id"],
            title=row["title"],
            status=row["status"],
            created_at=datetime.fromisoformat(row["created_at"]),
            cost_usd=float(row["cost_usd"] or 0.0),
            verdict=row["verdict"],
            output_formats=json.loads(row["output_formats"] or "[]"),
        )
        for row in rows
    ]


async def _delete_report_summary(session_id: str) -> None:
    await _ensure_reports_table()
    engine = create_async_engine(_db_url(), future=True)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM reports WHERE session_id = :session_id"),
                {"session_id": session_id},
            )
    finally:
        await engine.dispose()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_event(
    step: str,
    status: str,
    message: str = "",
    cost_usd: float = 0.0,
    tokens_used: int = 0,
    **extra,
) -> dict:
    ev = {
        "step": step,
        "status": status,
        "message": message,
        "cost_usd": cost_usd,
        "tokens_used": tokens_used,
        "timestamp": _now_iso(),
    }
    ev.update(extra)
    return ev


async def _push_event(session_id: str, event: dict) -> None:
    _session_events.setdefault(session_id, []).append(event)
    q = _session_queues.get(session_id)
    if q:
        await q.put(event)


async def _run_pipeline(session_id: str, body: CreateReportRequest) -> None:
    from backend.pipeline.graph import pipeline_context

    session = _sessions[session_id]
    session.status = "running"
    await _upsert_report_summary(session)
    await _push_event(session_id, _make_event("pipeline", "started", "Pipeline started"))
    checkpointer = None

    try:
        async with pipeline_context() as (graph, checkpointer):
            user_request = UserRequest(
                query=body.request,
                preferred_format=body.output_formats[0] if body.output_formats else None,
            )
            initial_state = {
                "session_id": session_id,
                "report_id": session_id,
                "original_request": body.request,
                "selected_depth": body.depth,
                "user_request": user_request.model_dump(),
                "status": ReportStatus.INTAKE,
                "messages": [],
                "cost_usd": 0.0,
                "revision_count": 0,
                "iteration": 0,
                "max_iterations": 3,
                "errors": [],
            }

            async for ev in graph.astream_events(
                initial_state,
                version="v2",
                config={
                    "recursion_limit": 50,
                    "configurable": {"thread_id": session_id},
                },
            ):
                event_type: str = ev.get("event", "")
                name: str = ev.get("name", "")

                if event_type == "on_chain_start" and name in STEP_LABELS:
                    await _push_event(
                        session_id,
                        _make_event(name, "started", STEP_LABELS[name], session.cost_usd, session.tokens_used),
                    )

                elif event_type == "on_chain_end" and name in STEP_LABELS:
                    output = ev.get("data", {}).get("output", {})
                    if isinstance(output, dict):
                        if "cost_usd" in output:
                            session.cost_usd = float(output["cost_usd"])
                        if output.get("report"):
                            try:
                                session.report = ReportOutput.model_validate(output["report"])
                            except Exception:
                                pass
                        if output.get("qa_result"):
                            qa_result = output["qa_result"]
                            if hasattr(qa_result, "verdict"):
                                verdict = qa_result.verdict
                                session.verdict = verdict.value if hasattr(verdict, "value") else str(verdict)
                            elif isinstance(qa_result, dict):
                                session.verdict = str(qa_result.get("verdict") or session.verdict or "")
                        if output.get("final_report_paths"):
                            for p in output["final_report_paths"]:
                                ext = os.path.splitext(p)[1].lstrip(".")
                                fmt = "presentation" if ext == "pptx" else ext
                                session.report_urls[fmt] = f"/api/reports/{session_id}/download/{fmt}"
                        await _upsert_report_summary(session)

                    await _push_event(
                        session_id,
                        _make_event(name, "done", STEP_LABELS[name], session.cost_usd, session.tokens_used),
                    )

                elif event_type == "on_chain_error" and name in STEP_LABELS:
                    err = str(ev.get("data", {}).get("error", "unknown"))
                    await _push_event(
                        session_id,
                        _make_event(name, "error", err, session.cost_usd, session.tokens_used),
                    )

            if session.verdict and session.verdict != "PASS":
                session.status = "failed"
                await _upsert_report_summary(session)
                await _push_event(
                    session_id,
                    _make_event(
                        "pipeline",
                        "error",
                        f"Pipeline stopped after QA verdict {session.verdict}",
                        session.cost_usd,
                        session.tokens_used,
                    ),
                )
            else:
                session.status = "completed"
                await _upsert_report_summary(session)
                await _push_event(
                    session_id,
                    _make_event(
                        "complete",
                        "done",
                        "Report generation complete",
                        session.cost_usd,
                        session.tokens_used,
                        report_urls=session.report_urls,
                    ),
                )

    except Exception as exc:
        logger.error(f"Pipeline failed for session {session_id}: {exc}")
        session.status = "failed"
        await _upsert_report_summary(session)
        await _push_event(
            session_id,
            _make_event("pipeline", "error", str(exc), session.cost_usd, session.tokens_used),
        )

    finally:
        if checkpointer is not None and hasattr(checkpointer, "close"):
            close_result = checkpointer.close()
            if asyncio.iscoroutine(close_result):
                await close_result
        q = _session_queues.get(session_id)
        if q:
            await q.put(None)


@router.post("/reports")
async def create_report(body: CreateReportRequest) -> dict:
    session_id = str(uuid.uuid4())
    session = SessionMeta(
        session_id=session_id,
        request=body.request,
        depth=body.depth,
        output_formats=body.output_formats,
        created_at=datetime.now(timezone.utc),
    )
    _sessions[session_id] = session
    _session_events[session_id] = []
    _session_queues[session_id] = asyncio.Queue()
    await _upsert_report_summary(session)

    asyncio.create_task(_run_pipeline(session_id, body))

    return {
        "session_id": session_id,
        "estimated_time_minutes": DEPTH_ESTIMATED_MINUTES.get(body.depth, 8),
    }


@router.get("/reports/pricing")
async def get_report_pricing() -> dict:
    return {"tiers": get_public_pricing()}


@router.get("/reports")
async def list_reports() -> list[dict]:
    summaries = await _list_report_summaries()
    return [summary.model_dump(mode="json") for summary in summaries]


@router.get("/reports/{session_id}/stream")
async def stream_report(session_id: str) -> EventSourceResponse:
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    async def generator() -> AsyncGenerator[dict, None]:
        for ev in list(_session_events.get(session_id, [])):
            yield {"data": json.dumps(ev)}

        session = _sessions[session_id]
        if session.status in ("completed", "failed"):
            return

        q = _session_queues[session_id]
        while True:
            ev = await q.get()
            if ev is None:
                break
            yield {"data": json.dumps(ev)}

    return EventSourceResponse(generator())


@router.get("/reports/{session_id}")
async def get_report(session_id: str) -> dict:
    if session_id in _sessions:
        session = _sessions[session_id]
        return {
            "session_id": session_id,
            "status": session.status,
            "cost_usd": session.cost_usd,
            "tokens_used": session.tokens_used,
            "report_urls": session.report_urls,
            "report": session.report.model_dump(mode="json") if session.report else None,
            "created_at": session.created_at.isoformat(),
        }

    # Fallback to DB (e.g. after server reload)
    try:
        engine = create_async_engine(_db_url(), future=True)
        try:
            async with engine.connect() as conn:
                result = await conn.execute(
                    text("SELECT session_id, title, status, created_at, cost_usd, verdict, output_formats FROM reports WHERE session_id = :sid"),
                    {"sid": session_id},
                )
                row = result.mappings().first()
        finally:
            await engine.dispose()
    except Exception as exc:
        logger.warning(f"DB fallback failed for {session_id}: {exc}")
        row = None

    if row is None:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "session_id": row["session_id"],
        "status": row["status"],
        "cost_usd": row["cost_usd"] or 0.0,
        "tokens_used": 0,
        "report_urls": {},
        "report": None,
        "created_at": row["created_at"],
        "title": row["title"],
    }


@router.get("/reports/{session_id}/download/{format}")
async def download_report(session_id: str, format: str) -> FileResponse:
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    ext_map = {
        "pdf": "pdf",
        "docx": "docx",
        "html": "html",
        "json": "json",
        "presentation": "pptx",
        "pptx": "pptx",
    }
    ext = ext_map.get(format)
    if not ext:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {format}")

    # renderer saves to {outputs_dir}/{session_id}/report.{ext}
    file_path = os.path.join(settings.outputs_dir, session_id, f"report.{ext}")
    if not os.path.exists(file_path):
        # fallback: flat layout {outputs_dir}/{session_id}.{ext}
        file_path = os.path.join(settings.outputs_dir, f"{session_id}.{ext}")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not ready or not found")

    media_types = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "html": "text/html",
        "json": "application/json",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    }
    return FileResponse(
        file_path,
        media_type=media_types[ext],
        filename=f"report_{session_id}.{ext}",
    )


@router.post("/reports/{session_id}/feedback")
async def submit_feedback(session_id: str, body: FeedbackRequest) -> dict:
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    _sessions[session_id].feedback = {
        "rating": body.rating,
        "comment": body.comment,
        "submitted_at": _now_iso(),
    }
    logger.info(f"Feedback saved for {session_id}: rating={body.rating}")
    return {"status": "ok"}


@router.post("/reports/{session_id}/subscribe")
async def subscribe_to_report(session_id: str, body: PushSubscriptionRequest) -> dict:
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    await save_push_subscription(session_id, body.model_dump())
    logger.info(f"Push subscription saved for session {session_id}")
    return {"status": "ok"}


@router.delete("/reports/{session_id}")
async def delete_report(session_id: str) -> dict:
    await _delete_report_summary(session_id)
    _sessions.pop(session_id, None)
    _session_events.pop(session_id, None)
    _session_queues.pop(session_id, None)
    logger.info(f"Report deleted: {session_id}")
    return {"status": "ok"}
