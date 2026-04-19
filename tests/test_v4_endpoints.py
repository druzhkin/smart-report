"""v4 HTTP layer — /api/v4/sessions and /generate-prompt (LLM mocked)."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from smart_report.api import app
from smart_report.api import v4_endpoints as v4
from smart_report.llm import LLMResult


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
        return LLMResult(text=json.dumps(_STUB, ensure_ascii=False), cost_rub=0.0)

    monkeypatch.setattr(pm_module, "call_json", _stub)


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


def test_v4_full_cycle(monkeypatch, tmp_path):
    """upload-reports → analyze → synthesize → export?format=md, all LLMs mocked."""
    from smart_report import analyzer as analyzer_module
    from smart_report import prompt_master as pm_module
    from smart_report import synthesizer as synth_module

    analyzer_payload = {
        "per_source_summary": [
            {"source": "perplexity", "summary": "s1", "strengths": "", "weaknesses": ""}
        ],
        "consensus": [
            {"claim": "shared claim", "supporting_sources": ["perplexity", "openai_dr"], "confidence": "high"}
        ],
        "conflicts": [
            {
                "topic": "mortgage",
                "source_a": "perplexity",
                "claim_a": "55%",
                "source_b": "openai_dr",
                "claim_b": "68%",
                "resolution_hint": "cross-check ERZ",
                "importance": "critical",
            }
        ],
        "gaps": [
            {"topic": "delivery", "why_critical": "speed", "what_to_find": "%", "candidate_sources": ["erzrf.ru"]}
        ],
        "unverified_numbers": [],
        "quality_notes": "ok",
        "followup_prompts": [
            {
                "prompt_id": "fp_01",
                "intent": "fill_gap",
                "prompt": "Find delay % on erzrf.ru for PIK, Donstroy.",
                "target_info": "delay",
                "suggested_tool": "perplexity",
                "suggested_source_site": "erzrf.ru",
                "priority": "must",
                "linked_to": "gap:delivery",
            }
        ],
    }

    synth_payload = {
        "session_id": "ignored",
        "question": "Q",
        "research_prompt_used": "R",
        "executive_summary": {
            "main_answer": "Product > speed > brand.",
            "ranking": "Продукт > скорость > бренд",
            "top_findings": ["Top-5 47%", "Mortgage 55%"],
            "key_numbers": [{"value": "47%", "metric": "top-5 share", "subject": "2024", "source_url": ""}],
            "confidence_note": "medium",
            "what_meta_adds": "resolved mortgage-share skew",
        },
        "main_synthesis": "## Позиция\n\nПродукт > скорость > бренд.",
        "consensus_section": "all agree on top-3.",
        "conflicts_section": "55 vs 68 — pick 55.",
        "gaps_filled_section": "delivery open.",
        "all_sources": [
            {"title": "ERZ", "url": "https://erzrf.ru/", "tool": "perplexity", "reliability": "high"}
        ],
        "metadata": {},
    }

    async def _pm_stub(*a, **kw):
        return LLMResult(
            text=json.dumps(
                {
                    "full_prompt": "X" * 250,
                    "reasoning": "r",
                    "expected_structure": ["s1"],
                    "key_entities": ["PIK"],
                    "tips_for_search": "Perplexity",
                },
                ensure_ascii=False,
            ),
            cost_rub=0.12,
        )

    async def _an_stub(*a, **kw):
        return LLMResult(text=json.dumps(analyzer_payload, ensure_ascii=False), cost_rub=0.12)

    async def _syn_stub(*a, **kw):
        return LLMResult(text=json.dumps(synth_payload, ensure_ascii=False), cost_rub=0.12)

    monkeypatch.setattr(pm_module, "call_json", _pm_stub)
    monkeypatch.setattr(analyzer_module, "call_json", _an_stub)
    monkeypatch.setattr(synth_module, "call_json", _syn_stub)

    client = TestClient(app)
    sid = client.post(
        "/api/v4/sessions", json={"question": "what drives success"}
    ).json()["session_id"]

    r = client.post(f"/api/v4/sessions/{sid}/generate-prompt")
    assert r.status_code == 200, r.text

    # Upload two source reports.
    files = [
        ("files", ("perplexity.md", b"# Perplexity sonar report\nPIK, Donstroy.", "text/markdown")),
        ("files", ("claude.md", b"# Claude analysis\nBusiness-class Moscow.", "text/markdown")),
    ]
    r = client.post(f"/api/v4/sessions/{sid}/upload-reports", files=files)
    assert r.status_code == 200, r.text
    uploaded = r.json()
    assert len(uploaded) == 2
    assert uploaded[0]["detected_tool"] in {"perplexity", "other"}
    assert uploaded[1]["detected_tool"] in {"claude", "other"}

    r = client.post(f"/api/v4/sessions/{sid}/analyze")
    assert r.status_code == 200, r.text
    analysis = r.json()
    assert len(analysis["consensus"]) == 1
    assert len(analysis["conflicts"]) == 1
    assert len(analysis["gaps"]) == 1
    assert len(analysis["followup_prompts"]) == 1

    r = client.post(f"/api/v4/sessions/{sid}/synthesize")
    assert r.status_code == 200, r.text
    final = r.json()
    assert final["session_id"] == sid
    assert final["executive_summary"]["main_answer"]
    assert final["executive_summary"]["ranking"].startswith("Продукт")

    # Export md
    r = client.get(f"/api/v4/sessions/{sid}/export", params={"format": "md"})
    assert r.status_code == 200, r.text
    assert "Продукт" in r.text or "Product" in r.text

    # Export json — also confirms content-type routing.
    r = client.get(f"/api/v4/sessions/{sid}/export", params={"format": "json"})
    assert r.status_code == 200
    # Export gamma-pdf stub.
    r = client.get(f"/api/v4/sessions/{sid}/export", params={"format": "gamma-pdf"})
    assert r.status_code == 200
    # Unknown format.
    r = client.get(f"/api/v4/sessions/{sid}/export", params={"format": "foo"})
    assert r.status_code == 400

    # Final session view.
    r = client.get(f"/api/v4/sessions/{sid}")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "synthesized"
    assert body["final_report"] is not None
    # Each of the 3 LLM steps returned cost_rub=0.12 → total should be 0.36.
    assert body["total_cost_rub"] == pytest.approx(0.36, abs=1e-3)


def test_track_b_endpoints_are_wired():
    """Track B has shipped — analyze/synthesize/upload routes exist (body behaviour
    is covered by test_v4_full_cycle / test_analyzer / test_synthesizer)."""
    client = TestClient(app)
    sid = client.post("/api/v4/sessions", json={"question": "what drives it"}).json()["session_id"]
    # analyze with no uploads → 400 (not 501)
    r = client.post(f"/api/v4/sessions/{sid}/analyze")
    assert r.status_code == 400, r.text
    # synthesize before analyze → 400
    r = client.post(f"/api/v4/sessions/{sid}/synthesize")
    assert r.status_code == 400, r.text
    # upload-reports without files → 422 (FastAPI rejects missing multipart)
    r = client.post(f"/api/v4/sessions/{sid}/upload-reports")
    assert r.status_code == 422, r.text
    # export before final_report exists → 409
    r = client.get(f"/api/v4/sessions/{sid}/export", params={"format": "md"})
    assert r.status_code == 409, r.text
