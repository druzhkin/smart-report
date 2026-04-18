"""FastAPI integration tests (mock LLM path, no network)."""

from __future__ import annotations

import asyncio
import re

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from smart_report.api import app
from smart_report.api.jobs import JOBS


@pytest.fixture(autouse=True)
def _clear_jobs():
    JOBS.clear()
    yield
    JOBS.clear()


def test_health():
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_create_research_and_wait_for_done():
    """End-to-end via mock path: POST /api/research, poll until done, fetch report."""
    # Patch the orchestrator inside api.main to use dry_run=True so the test is deterministic.
    from smart_report.api import main as api_main
    from smart_report.orchestrator import run as _real_run

    async def _mock_run(question, dry_run=False, *, emitter=None):
        return await _real_run(question, dry_run=True, emitter=emitter)

    original = api_main.run_orchestrator
    api_main.run_orchestrator = _mock_run
    try:
        client = TestClient(app)
        r = client.post("/api/research", json={"question": "why do developers succeed?"})
        assert r.status_code == 200, r.text
        job_id = r.json()["id"]
        assert r.json()["status"] == "pending"

        # Poll events until status terminal (test client runs bg task in same loop).
        cursor = 0
        status = "pending"
        for _ in range(30):
            ev = client.get(
                f"/api/research/{job_id}/events",
                params={"since": cursor, "timeout": 2},
            )
            assert ev.status_code == 200
            body = ev.json()
            cursor = body["cursor"]
            status = body["status"]
            if status in ("done", "error"):
                break
        assert status == "done", f"status={status}, last events: {body}"

        # Final report
        rep = client.get(f"/api/research/{job_id}")
        assert rep.status_code == 200
        payload = rep.json()
        assert payload["status"] == "done"
        assert payload["report"] is not None
        assert payload["report"]["summary"]["main_finding"]
    finally:
        api_main.run_orchestrator = original


def test_events_404_for_unknown_job():
    client = TestClient(app)
    r = client.get("/api/research/no-such-id/events")
    assert r.status_code == 404


def test_research_404_for_unknown_job():
    client = TestClient(app)
    r = client.get("/api/research/no-such-id")
    assert r.status_code == 404


def test_emits_contract_compatible_messages():
    """Events must carry scout '[cell_id]', analyst 'готов', bisociator 'Найдено связей:'."""
    from smart_report.api import main as api_main
    from smart_report.orchestrator import run as _real_run

    async def _mock_run(question, dry_run=False, *, emitter=None):
        return await _real_run(question, dry_run=True, emitter=emitter)

    original = api_main.run_orchestrator
    api_main.run_orchestrator = _mock_run
    try:
        client = TestClient(app)
        r = client.post("/api/research", json={"question": "probe"})
        job_id = r.json()["id"]
        cursor = 0
        collected: list[dict] = []
        for _ in range(30):
            ev = client.get(
                f"/api/research/{job_id}/events",
                params={"since": cursor, "timeout": 2},
            )
            body = ev.json()
            collected.extend(body["events"])
            cursor = body["cursor"]
            if body["status"] in ("done", "error"):
                break

        scout_msgs = [e["message"] for e in collected if e["phase"] == "scout"]
        analyst_msgs = [e["message"] for e in collected if e["phase"] == "analyst"]
        bisoc_msgs = [e["message"] for e in collected if e["phase"] == "bisociator"]
        assert all(m.startswith("[") for m in scout_msgs), scout_msgs
        assert any("готов" in m.lower() for m in analyst_msgs), analyst_msgs
        assert any(re.search(r"Найдено связей:\s*\d+", m) for m in bisoc_msgs), bisoc_msgs
    finally:
        api_main.run_orchestrator = original


def test_reports_list_endpoint():
    client = TestClient(app)
    r = client.get("/api/reports")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
