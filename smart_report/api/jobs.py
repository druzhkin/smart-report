"""In-memory job registry + JobEmitter — bridges orchestrator events to HTTP transports."""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

from ..events import EventEmitter, ALLOWED_PHASES
from ..models import Report


JobStatus = str  # "pending" | "running" | "done" | "error"


class Job:
    """Holds everything an HTTP client might ask for about one research run."""

    def __init__(self, job_id: str, question: str) -> None:
        self.id = job_id
        self.question = question
        self.status: JobStatus = "pending"
        self.error: str | None = None
        self.report: Report | None = None
        self.events: list[dict[str, Any]] = []
        self.created_at = time.time()
        self.finished_at: float | None = None
        # Signalled every time a new event is appended; long-poll waiters arm on it.
        self._new_event = asyncio.Event()
        self.task: asyncio.Task | None = None

    def append_event(self, ev: dict[str, Any]) -> None:
        self.events.append(ev)
        # cap to avoid unbounded memory; keep last 2000
        if len(self.events) > 2000:
            self.events = self.events[-1500:]
        self._new_event.set()

    def mark_status(self, status: JobStatus, *, error: str | None = None) -> None:
        self.status = status
        if error is not None:
            self.error = error
        if status in ("done", "error"):
            self.finished_at = time.time()
        # Wake long-poll waiters so they can observe the status change.
        self._new_event.set()

    async def wait_for_events(self, since: int, timeout: float) -> None:
        """Block up to `timeout` until events count grows past `since` or status moves to terminal."""
        if len(self.events) > since or self.status in ("done", "error"):
            return
        self._new_event.clear()
        try:
            await asyncio.wait_for(self._new_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            return


class JobEmitter(EventEmitter):
    """EventEmitter that pushes into a Job's event list."""

    def __init__(self, job: Job) -> None:
        self.job = job

    def emit(self, phase: str, message: str, *, data: dict[str, Any] | None = None) -> None:
        if phase not in ALLOWED_PHASES:
            phase = "status"  # defensive — never let a stray phase break a contract
        ev = {
            "seq": len(self.job.events),
            "phase": phase,
            "message": message,
            "data": data,
            "ts": time.time(),
        }
        self.job.append_event(ev)


# Module-level registry; process-local (acceptable for MVP single-worker uvicorn).
JOBS: dict[str, Job] = {}


def new_job_id() -> str:
    return uuid.uuid4().hex[:12]


def get_job(job_id: str) -> Job | None:
    return JOBS.get(job_id)


def register(job: Job) -> None:
    JOBS[job.id] = job


def list_jobs() -> list[Job]:
    return sorted(JOBS.values(), key=lambda j: j.created_at, reverse=True)
