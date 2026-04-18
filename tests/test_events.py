"""EventEmitter contract + orchestrator emit-point tests (mock path only)."""

from __future__ import annotations

import asyncio
import re

from smart_report.events import ALLOWED_PHASES, EventEmitter, ListEmitter, NullEmitter
from smart_report.orchestrator import run


def test_null_emitter_is_an_event_emitter():
    em = NullEmitter()
    assert isinstance(em, EventEmitter)
    em.emit("status", "noop")
    em.emit("error", "x", data={"foo": "bar"})


def test_list_emitter_captures_events():
    em = ListEmitter()
    em.emit("status", "a")
    em.emit("planner", "b", data={"n": 1})
    assert len(em.events) == 2
    assert em.events[0]["phase"] == "status"
    assert em.events[1]["message"] == "b"
    assert em.events[1]["data"] == {"n": 1}
    assert all("ts" in e for e in em.events)


def test_orchestrator_emits_full_lifecycle_mock():
    em = ListEmitter()
    asyncio.run(run("probe question", dry_run=True, emitter=em))
    phases = [e["phase"] for e in em.events]
    # every expected phase fires at least once
    for expected in ["status", "planner", "scout", "analyst", "bisociator", "summarizer", "done"]:
        assert expected in phases, f"missing phase {expected}; got {phases}"


def test_orchestrator_runs_without_emitter():
    """Back-compat: existing CLI callers pass no emitter."""
    report = asyncio.run(run("probe", dry_run=True))
    assert report.summary is not None


def test_scout_events_start_with_bracket_cell_id():
    """Frontend LivePipeline regex depends on scout messages starting with `[cell_id]`."""
    em = ListEmitter()
    asyncio.run(run("probe", dry_run=True, emitter=em))
    scout_msgs = [e["message"] for e in em.events if e["phase"] == "scout"]
    assert scout_msgs, "no scout events emitted"
    assert all(m.startswith("[") for m in scout_msgs), scout_msgs


def test_analyst_done_event_contains_gotov():
    """Frontend counts completed blocks by matching /готов/ in analyst messages."""
    em = ListEmitter()
    asyncio.run(run("probe", dry_run=True, emitter=em))
    analyst_done = [
        e["message"]
        for e in em.events
        if e["phase"] == "analyst" and "готов" in e["message"].lower()
    ]
    assert len(analyst_done) >= 1, [e["message"] for e in em.events if e["phase"] == "analyst"]


def test_bisociator_done_has_n_found():
    """Frontend extracts link count via /Найдено связей:\\s*(\\d+)/."""
    em = ListEmitter()
    asyncio.run(run("probe", dry_run=True, emitter=em))
    bisociator_msgs = [e["message"] for e in em.events if e["phase"] == "bisociator"]
    found = [m for m in bisociator_msgs if re.search(r"Найдено связей:\s*\d+", m)]
    assert len(found) >= 1, bisociator_msgs


def test_all_phases_are_whitelisted():
    em = ListEmitter()
    asyncio.run(run("probe", dry_run=True, emitter=em))
    for e in em.events:
        assert e["phase"] in ALLOWED_PHASES, e


def test_done_event_carries_run_dir_and_counts():
    em = ListEmitter()
    asyncio.run(run("probe", dry_run=True, emitter=em))
    done = [e for e in em.events if e["phase"] == "done"]
    assert len(done) == 1
    d = done[0]["data"]
    assert "run_dir" in d
    assert "n_cells" in d and d["n_cells"] >= 1
    assert "n_cross_links" in d
    assert "question_id" in d
