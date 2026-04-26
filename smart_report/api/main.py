"""FastAPI app: POST /api/research starts a job; events via long-poll or SSE; reports listed/fetched."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from ..io import RUNS_DIR
from ..orchestrator import run as run_orchestrator
from .jobs import (
    JOBS,
    Job,
    JobEmitter,
    get_job,
    list_jobs,
    new_job_id,
    register,
)
from .models import JobSummary, ResearchIn, ResearchOut
from .v4_endpoints import router as v4_router
from .landing import router as landing_router

log = logging.getLogger("smart_report.api")

app = FastAPI(title="smart-report-mvp-v3 API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "http://localhost:3002",
        "http://127.0.0.1:3002",
        "http://localhost:3003",
        "http://127.0.0.1:3003",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(v4_router)
app.include_router(landing_router)


# ---------- runtime ----------

async def _run_job(job: Job) -> None:
    job.mark_status("running")
    emitter = JobEmitter(job)
    try:
        report = await run_orchestrator(job.question, dry_run=False, emitter=emitter)
        job.report = report
        job.mark_status("done")
    except Exception as err:
        log.exception("job %s failed: %s", job.id, err)
        job.mark_status("error", error=f"{type(err).__name__}: {err}")


# ---------- endpoints ----------


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/research", response_model=ResearchOut)
async def start_research(
    payload: ResearchIn, background: BackgroundTasks
) -> ResearchOut:
    job = Job(job_id=new_job_id(), question=payload.question)
    register(job)
    background.add_task(_run_job, job)
    return ResearchOut(id=job.id, status="pending")


@app.get("/api/research/{job_id}/events")
async def get_events(job_id: str, since: int = 0, timeout: float = 25.0) -> dict[str, Any]:
    """Long-poll: return events with seq >= since, waiting up to `timeout` seconds for new ones."""
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"job {job_id} not found")
    # Clamp timeout: [0, 30]
    timeout = max(0.0, min(float(timeout), 30.0))
    await job.wait_for_events(since=since, timeout=timeout)
    new_events = job.events[since:]
    return {
        "events": new_events,
        "cursor": since + len(new_events),
        "status": job.status,
        "error": job.error,
    }


@app.get("/api/research/{job_id}/stream")
async def stream(job_id: str, request: Request) -> StreamingResponse:
    """SSE fallback. Long-poll is preferred behind Railway/CloudFront."""
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"job {job_id} not found")

    async def gen():
        yield ": connected\n\n"
        cursor = 0
        while True:
            if await request.is_disconnected():
                break
            await job.wait_for_events(since=cursor, timeout=15.0)
            new_events = job.events[cursor:]
            for ev in new_events:
                payload = json.dumps(ev, ensure_ascii=False, default=str)
                yield f"event: {ev['phase']}\ndata: {payload}\n\n"
            cursor += len(new_events)
            if job.status in ("done", "error"):
                yield f"event: close\ndata: {json.dumps({'status': job.status, 'error': job.error})}\n\n"
                break
            if not new_events:
                yield ": keepalive\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.get("/api/research/{job_id}")
async def get_research(job_id: str) -> dict[str, Any]:
    job = get_job(job_id)
    if job is None:
        # fallback: on-disk run
        raw = _read_disk_report(job_id)
        if raw is None:
            raise HTTPException(status_code=404, detail=f"job {job_id} not found")
        return {
            "id": job_id,
            "status": "done",
            "error": None,
            "report": raw,
            "source": "disk",
        }
    return {
        "id": job.id,
        "status": job.status,
        "error": job.error,
        "report": job.report.model_dump() if job.report else None,
        "source": "memory",
    }


@app.get("/api/reports")
async def get_reports() -> list[dict[str, Any]]:
    """Return jobs currently in memory plus on-disk runs from runs/*/raw.json."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []

    # In-memory jobs first (most recent state).
    for j in list_jobs():
        seen.add(j.id)
        out.append(
            JobSummary(
                id=j.id,
                question=j.question,
                status=j.status,
                created_at=j.created_at,
                finished_at=j.finished_at,
                error=j.error,
            ).model_dump()
        )

    # Disk runs.
    if RUNS_DIR.exists():
        for run_dir in sorted(RUNS_DIR.iterdir(), reverse=True):
            if not run_dir.is_dir() or run_dir.name in seen:
                continue
            raw_path = run_dir / "raw.json"
            if not raw_path.exists():
                continue
            try:
                data = json.loads(raw_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            q = (data.get("question") or {}).get("text", "")
            out.append(
                {
                    "id": run_dir.name,
                    "question": q,
                    "status": "done",
                    "created_at": run_dir.stat().st_mtime,
                    "finished_at": run_dir.stat().st_mtime,
                    "error": None,
                }
            )

    return out


# ---------- helpers ----------


def _read_disk_report(job_id: str) -> dict | None:
    candidate: Path = RUNS_DIR / job_id / "raw.json"
    if not candidate.exists():
        return None
    try:
        return json.loads(candidate.read_text(encoding="utf-8"))
    except Exception:
        return None
