"""v4 HTTP layer — /api/v4/sessions and /generate-prompt (LLM mocked)."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from smart_report.api import app
from smart_report.api import v4_endpoints as v4


_STUB = {
    "full_prompt": (
        "Goal: determine whether brand, speed, or product quality best explains "
        "commercial success for developers in Moscow's business-class segment "
        "between 2023 and 2025. Analyse the nine named developers (PIK, Donstroy, "
        "MR Group, Level Group, Etalon, Sminex, Capital Group, FSK, A101) across "
        "six structured sections with URL-cited figures from ERZ, bnMAP, and "
        "CIAN Pro. Forbid hedging — pick a driver and defend it."
    ),
    "reasoning": "Names 9 developers and 3 canonical data sources; demands a position.",
    "expected_structure": ["Scoring", "Brand", "Speed", "Product", "Correlation", "Limits"],
    "key_entities": ["PIK", "Donstroy", "MR Group", "ERZ"],
    "tips_for_search": "Perplexity DR for figures, OpenAI DR for narrative.",
}


@pytest.fixture(autouse=True)
def _reset_state():
    v4._V4_SESSIONS.clear()
    v4._V4_EVENTS.clear()
    v4._V4_EVENT_SIGNALS.clear()
    yield
    v4._V4_SESSIONS.clear()
    v4._V4_EVENTS.clear()
    v4._V4_EVENT_SIGNALS.clear()


@pytest.fixture
def mock_llm(monkeypatch):
    from smart_report import prompt_master as pm_module

    async def _stub(*args, **kwargs):
        return json.dumps(_STUB, ensure_ascii=False)

    monkeypatch.setattr(pm_module, "chat", _stub)


def test_create_session_returns_session_id():
    client = TestClient(app)
    r = client.post("/api/v4/sessions", json={"question": "what drives developer success"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "session_id" in body
    assert len(body["session_id"]) == 12


def test_create_session_rejects_short_question():
    client = TestClient(app)
    r = client.post("/api/v4/sessions", json={"question": "hi"})
    assert r.status_code == 422


def test_generate_prompt_end_to_end(mock_llm):
    client = TestClient(app)
    r = client.post("/api/v4/sessions", json={"question": "market analysis please"})
    sid = r.json()["session_id"]

    r2 = client.post(f"/api/v4/sessions/{sid}/generate-prompt")
    assert r2.status_code == 200, r2.text
    data = r2.json()
    assert data["full_prompt"].startswith("Goal:")
    assert len(data["full_prompt"]) > 200
    assert "PIK" in data["key_entities"]
    assert len(data["expected_structure"]) == 6


def test_generate_prompt_404_on_unknown_session():
    client = TestClient(app)
    r = client.post("/api/v4/sessions/no-such-id/generate-prompt")
    assert r.status_code == 404


def test_get_session_after_prompt_generation(mock_llm):
    client = TestClient(app)
    sid = client.post("/api/v4/sessions", json={"question": "what drives it"}).json()["session_id"]
    client.post(f"/api/v4/sessions/{sid}/generate-prompt")
    r = client.get(f"/api/v4/sessions/{sid}")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "prompt_ready"
    assert body["research_prompt"] is not None
    assert body["research_prompt"]["full_prompt"].startswith("Goal:")


def test_events_route_returns_prompt_master_events(mock_llm):
    client = TestClient(app)
    sid = client.post("/api/v4/sessions", json={"question": "what drives it"}).json()["session_id"]
    client.post(f"/api/v4/sessions/{sid}/generate-prompt")
    r = client.get(f"/api/v4/sessions/{sid}/events", params={"since": 0, "timeout": 0})
    assert r.status_code == 200
    body = r.json()
    phases = [e["phase"] for e in body["events"]]
    assert "prompt_master" in phases


def test_track_b_stubs_return_501():
    client = TestClient(app)
    sid = client.post("/api/v4/sessions", json={"question": "what drives it"}).json()["session_id"]
    for path in ("upload-reports", "analyze", "upload-followup", "synthesize"):
        r = client.post(f"/api/v4/sessions/{sid}/{path}")
        assert r.status_code == 501, f"{path} returned {r.status_code}"
    r = client.get(f"/api/v4/sessions/{sid}/export")
    assert r.status_code == 501
