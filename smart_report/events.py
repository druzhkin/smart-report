"""Event emitter for pipeline progress. Orchestrator emits; transport (SSE/poll) owns how to deliver."""

from __future__ import annotations

import time
from typing import Any, Protocol, runtime_checkable


ALLOWED_PHASES = {
    "status",
    "planner",
    "scout",
    "analyst",
    "bisociator",
    "summarizer",
    "done",
    "error",
    # v4 meta-analysis phases
    "prompt_master",
    "external_research",
    "analyzer",
    "synthesizer",
}


@runtime_checkable
class EventEmitter(Protocol):
    def emit(self, phase: str, message: str, *, data: dict[str, Any] | None = None) -> None: ...


class NullEmitter:
    """Default emitter for CLI/tests — swallows every event."""

    def emit(self, phase: str, message: str, *, data: dict[str, Any] | None = None) -> None:
        return None


class ListEmitter:
    """Captures events in memory. Used by tests and by api/jobs.py (Part C)."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def emit(self, phase: str, message: str, *, data: dict[str, Any] | None = None) -> None:
        self.events.append(
            {
                "phase": phase,
                "message": message,
                "data": data,
                "ts": time.time(),
            }
        )
