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
def _reset_state(tmp_path, monkeypatch):
    v4._V4_SESSIONS.clear()
    v4._V4_EVENTS.clear()
    v4._V4_EVENT_SIGNALS.clear()
    # Per-user isolation + cost cap require an authenticated user. Isolate
    # the auth user store to a temp file per test and clear the in-memory
    # signup rate-limit so repeated tests don't 429 each other.
    from smart_report.api import auth as auth_module
    monkeypatch.setattr(auth_module, "_DATA_DIR", tmp_path / "auth")
    monkeypatch.setattr(auth_module, "_USERS_PATH", tmp_path / "auth" / "users.json")
    auth_module._SIGNUP_RATE.clear()
    yield
    v4._V4_SESSIONS.clear()
    v4._V4_EVENTS.clear()
    v4._V4_EVENT_SIGNALS.clear()


def _authed_client():
    """TestClient with a fresh signed-up user — sets the session cookie so
    POST /api/v4/sessions and the per-user-gated endpoints accept calls."""
    c = TestClient(app)
    r = c.post(
        "/api/auth/signup",
        json={"email": "tester@example.com", "password": "test1234"},
    )
    assert r.status_code == 201, r.text
    return c


def _await_long_task(client, sid: str, task_id: str, timeout: float = 5.0) -> dict:
    """Poll /long-task-status until terminal, return the final status body.

    Used by tests that submit /analyze or /synthesize and need the
    background asyncio.Task to finish before asserting on results.
    With LLM stubs the task usually completes within the first few
    polls; the timeout is a guardrail.
    """
    import time
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        r = client.get(
            f"/api/v4/sessions/{sid}/long-task-status",
            params={"task_id": task_id},
        )
        assert r.status_code == 200, r.text
        last = r.json()
        if last["state"] in ("completed", "failed"):
            return last
        time.sleep(0.02)
    raise AssertionError(
        f"long-task {task_id} did not reach terminal state in {timeout}s; "
        f"last poll: {last}"
    )


@pytest.fixture
def mock_llm(monkeypatch):
    from smart_report import prompt_master as pm_module

    async def _stub(*args, **kwargs):
        return LLMResult(text=json.dumps(_STUB, ensure_ascii=False), cost_rub=0.0)

    monkeypatch.setattr(pm_module, "call_json", _stub)


def test_create_session_returns_session_id():
    client = _authed_client()
    r = client.post("/api/v4/sessions", json={"question": "what drives developer success"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "session_id" in body
    assert len(body["session_id"]) == 12


def test_create_session_rejects_short_question():
    client = _authed_client()
    r = client.post("/api/v4/sessions", json={"question": "hi"})
    assert r.status_code == 422


def test_generate_prompt_end_to_end(mock_llm):
    client = _authed_client()
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
    client = _authed_client()
    r = client.post("/api/v4/sessions/no-such-id/generate-prompt")
    assert r.status_code == 404


def test_get_session_after_prompt_generation(mock_llm):
    client = _authed_client()
    sid = client.post("/api/v4/sessions", json={"question": "what drives it"}).json()["session_id"]
    client.post(f"/api/v4/sessions/{sid}/generate-prompt")
    r = client.get(f"/api/v4/sessions/{sid}")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "prompt_ready"
    assert body["research_prompt"] is not None
    assert body["research_prompt"]["full_prompt"].startswith("Goal:")


def test_events_route_returns_prompt_master_events(mock_llm):
    client = _authed_client()
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

    async def _intake_stub(*a, **kw):
        return LLMResult(
            text=json.dumps({"numeric_facts": [], "qualitative_facts": [], "claims": []}),
            cost_rub=0.0,
        )

    async def _critic_stub(*a, **kw):
        return LLMResult(
            text=json.dumps({"issues": [], "severity_summary": {"critical": 0, "material": 0, "minor": 0}, "overall_verdict": "pass"}),
            cost_rub=0.0,
        )

    monkeypatch.setattr(pm_module, "call_json", _pm_stub)
    monkeypatch.setattr(analyzer_module, "call_json", _an_stub)
    monkeypatch.setattr(synth_module, "call_json", _syn_stub)
    from smart_report import intake as intake_module
    from smart_report import synthesis_critic as critic_module
    monkeypatch.setattr(intake_module, "call_json", _intake_stub)
    monkeypatch.setattr(critic_module, "call_json", _critic_stub)

    client = _authed_client()
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
    assert r.status_code == 202, r.text
    task = r.json()
    assert task["phase"] == "analyze"
    assert task["state"] == "running"
    status = _await_long_task(client, sid, task["task_id"])
    assert status["state"] == "completed", status
    # Result lives on the session, not in the 202 body.
    sess = client.get(f"/api/v4/sessions/{sid}").json()
    analysis = sess["analysis"]
    assert len(analysis["consensus"]) == 1
    assert len(analysis["conflicts"]) == 1
    assert len(analysis["gaps"]) == 1
    assert len(analysis["followup_prompts"]) == 1

    r = client.post(f"/api/v4/sessions/{sid}/synthesize")
    assert r.status_code == 202, r.text
    task = r.json()
    assert task["phase"] == "synthesize"
    status = _await_long_task(client, sid, task["task_id"])
    assert status["state"] == "completed", status
    sess = client.get(f"/api/v4/sessions/{sid}").json()
    final = sess["final_report"]
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


def test_auto_dr_appends_to_source_reports(monkeypatch):
    """Mock auto_dr.run_auto_dr → returns a fake markdown; verify endpoint
    appends to source_reports + bumps cost + flips status."""
    from smart_report.models import UploadedMarkdown
    from smart_report.sources import auto_dr as auto_dr_mod

    async def _fake_run(service, question, *, domain_hint=None, max_results=10):
        return auto_dr_mod.AutoDRResult(
            upload=UploadedMarkdown(
                filename=f"auto_dr_{service}.md",
                content=f"# {service} stub\n\nfake markdown",
                detected_tool="other",
                word_count=4,
            ),
            service=service,
            cost_usd=0.005,
            cost_rub=0.377,
            source_count=3,
            notes="stub",
        )

    monkeypatch.setattr(auto_dr_mod, "run_auto_dr", _fake_run)

    client = _authed_client()
    sid = client.post(
        "/api/v4/sessions", json={"question": "test research question"}
    ).json()["session_id"]

    r = client.post(
        f"/api/v4/sessions/{sid}/auto-dr",
        json={"service": "tavily", "prompt": "find me X"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["service"] == "tavily"
    assert body["source_count"] == 3
    assert body["cost_usd"] == pytest.approx(0.005, abs=1e-6)

    # Session state mutated: source_reports has the new upload, status flipped.
    sess = client.get(f"/api/v4/sessions/{sid}").json()
    assert len(sess["source_reports"]) == 1
    assert sess["source_reports"][0]["filename"] == "auto_dr_tavily.md"
    assert sess["status"] == "reports_uploaded"
    assert sess["total_cost_rub"] == pytest.approx(0.377, abs=1e-3)


def test_auto_dr_rejects_unknown_service():
    client = _authed_client()
    sid = client.post(
        "/api/v4/sessions", json={"question": "test research question"}
    ).json()["session_id"]
    r = client.post(
        f"/api/v4/sessions/{sid}/auto-dr",
        json={"service": "google", "prompt": "x"},
    )
    # pydantic Literal validation rejects unknown service before reaching handler
    assert r.status_code == 422, r.text


def test_auto_dr_surfaces_backend_error_as_502(monkeypatch):
    from smart_report.sources import auto_dr as auto_dr_mod

    async def _fail(*args, **kwargs):
        raise auto_dr_mod.AutoDRError("valyu returned empty/error: no results")

    monkeypatch.setattr(auto_dr_mod, "run_auto_dr", _fail)

    client = _authed_client()
    sid = client.post(
        "/api/v4/sessions", json={"question": "test research question"}
    ).json()["session_id"]
    r = client.post(
        f"/api/v4/sessions/{sid}/auto-dr",
        json={"service": "valyu", "prompt": "obscure thing"},
    )
    assert r.status_code == 502, r.text
    assert "valyu" in r.json()["detail"].lower()


def test_auto_dr_falls_back_to_session_question_when_prompt_empty(monkeypatch):
    """If client omits `prompt`, the endpoint reuses the session's question
    (or the generated research_prompt) — UX optimization for the picker
    that fires before the user has manually edited the prompt."""
    from smart_report.models import UploadedMarkdown
    from smart_report.sources import auto_dr as auto_dr_mod

    captured = {}

    async def _capture(service, question, *, domain_hint=None, max_results=10):
        captured["question"] = question
        return auto_dr_mod.AutoDRResult(
            upload=UploadedMarkdown(
                filename="x.md", content="x", detected_tool="other", word_count=1,
            ),
            service=service,
            cost_usd=0.0, cost_rub=0.0, source_count=0, notes="",
        )

    monkeypatch.setattr(auto_dr_mod, "run_auto_dr", _capture)

    client = _authed_client()
    sid = client.post(
        "/api/v4/sessions", json={"question": "what is the meaning of life"}
    ).json()["session_id"]
    r = client.post(
        f"/api/v4/sessions/{sid}/auto-dr",
        json={"service": "tavily"},  # no prompt
    )
    assert r.status_code == 200, r.text
    assert captured["question"] == "what is the meaning of life"


def test_cancel_marks_session_and_blocks_further_spend():
    client = _authed_client()
    sid = client.post(
        "/api/v4/sessions", json={"question": "test research question"}
    ).json()["session_id"]

    r = client.post(f"/api/v4/sessions/{sid}/cancel")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "cancelled"

    sess = client.get(f"/api/v4/sessions/{sid}").json()
    assert sess["status"] == "cancelled"

    # Any LLM-spending endpoint now 409s.
    r2 = client.post(f"/api/v4/sessions/{sid}/generate-prompt")
    assert r2.status_code == 409, r2.text
    assert "cancel" in r2.json()["detail"].lower()


def test_cancel_is_idempotent():
    client = _authed_client()
    sid = client.post(
        "/api/v4/sessions", json={"question": "test research question"}
    ).json()["session_id"]
    r1 = client.post(f"/api/v4/sessions/{sid}/cancel")
    r2 = client.post(f"/api/v4/sessions/{sid}/cancel")
    assert r1.status_code == 200 and r2.status_code == 200
    assert r2.json()["status"] == "cancelled"


def test_delete_removes_session_and_returns_204():
    client = _authed_client()
    sid = client.post(
        "/api/v4/sessions", json={"question": "test research question"}
    ).json()["session_id"]

    r = client.delete(f"/api/v4/sessions/{sid}")
    assert r.status_code == 204, r.text

    # GET is now 404 (session gone).
    r2 = client.get(f"/api/v4/sessions/{sid}")
    assert r2.status_code == 404


def test_delete_404s_when_session_missing():
    client = _authed_client()
    r = client.delete("/api/v4/sessions/doesnotexist00")
    assert r.status_code == 404


def test_delete_403s_when_not_owner():
    """Owner of session A cannot DELETE session of user B."""
    # User B creates a session
    cb = TestClient(app)
    rb = cb.post("/api/auth/signup", json={"email": "userb@example.com", "password": "test1234"})
    assert rb.status_code == 201, rb.text
    sid = cb.post("/api/v4/sessions", json={"question": "user b's question"}).json()["session_id"]
    # User A tries to delete it
    ca = _authed_client()
    r = ca.delete(f"/api/v4/sessions/{sid}")
    assert r.status_code == 403, r.text


def test_auto_dr_async_path_returns_task_id_and_charges_upfront(monkeypatch):
    """When mode is set, auto-dr submits a Valyu Research job and returns task_id."""
    from smart_report.sources import auto_dr as auto_dr_mod

    submitted: dict = {}

    async def _fake_submit(service, question, *, mode="standard", session_id=None, store=None):
        submitted["service"] = service
        submitted["question"] = question
        submitted["mode"] = mode
        return auto_dr_mod.AsyncResearchSubmission(
            task_id="task-xyz-123",
            service="valyu",
            mode=mode,
            cost_usd=0.50,
            eta_min_low=10,
            eta_min_high=20,
        )

    monkeypatch.setattr(auto_dr_mod, "submit_async_research", _fake_submit)

    client = _authed_client()
    sid = client.post(
        "/api/v4/sessions", json={"question": "test research async flow"}
    ).json()["session_id"]

    r = client.post(
        f"/api/v4/sessions/{sid}/auto-dr",
        json={"service": "valyu", "mode": "standard", "prompt": "deep dive on X"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["task_id"] == "task-xyz-123"
    assert body["mode"] == "standard"
    assert body["cost_usd"] == pytest.approx(0.50)
    assert body["eta_min_low"] == 10
    assert "10–20" in body["message"] or "10-20" in body["message"]

    # Cost charged upfront, job tracked in pending_dr_jobs
    sess = client.get(f"/api/v4/sessions/{sid}").json()
    assert len(sess["pending_dr_jobs"]) == 1
    assert sess["pending_dr_jobs"][0]["task_id"] == "task-xyz-123"
    assert sess["total_cost_rub"] > 30  # 0.50 * 75.4 = ~37


def test_auto_dr_status_running_returns_state(monkeypatch):
    from smart_report.sources import auto_dr as auto_dr_mod

    async def _fake_submit(service, question, *, mode="standard", session_id=None, store=None):
        return auto_dr_mod.AsyncResearchSubmission(
            task_id="t1", service="valyu", mode=mode,
            cost_usd=0.50, eta_min_low=10, eta_min_high=20,
        )

    async def _fake_poll(task_id, *, service="valyu", mode="standard"):
        return auto_dr_mod.AsyncResearchPoll(state="running", progress_pct=42, message="searching…")

    monkeypatch.setattr(auto_dr_mod, "submit_async_research", _fake_submit)
    monkeypatch.setattr(auto_dr_mod, "try_collect_async_research", _fake_poll)

    client = _authed_client()
    sid = client.post(
        "/api/v4/sessions", json={"question": "test research async flow"}
    ).json()["session_id"]
    client.post(
        f"/api/v4/sessions/{sid}/auto-dr",
        json={"service": "valyu", "mode": "standard", "prompt": "x"},
    )
    r = client.get(f"/api/v4/sessions/{sid}/auto-dr-status?task_id=t1")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["state"] == "running"
    assert body["progress_pct"] == 42


def test_auto_dr_status_completed_appends_to_source_reports(monkeypatch):
    from smart_report.models import UploadedMarkdown
    from smart_report.sources import auto_dr as auto_dr_mod

    async def _fake_submit(service, question, *, mode="standard", session_id=None, store=None):
        return auto_dr_mod.AsyncResearchSubmission(
            task_id="t2", service="valyu", mode=mode,
            cost_usd=0.50, eta_min_low=10, eta_min_high=20,
        )

    async def _fake_poll(task_id, *, service="valyu", mode="standard"):
        return auto_dr_mod.AsyncResearchPoll(
            state="completed",
            result=auto_dr_mod.AutoDRResult(
                upload=UploadedMarkdown(
                    filename="valyu_research_standard_t2.md",
                    content="# Final report\n\nSome findings.",
                    detected_tool="other",
                    word_count=4,
                ),
                service="valyu",
                cost_usd=0.50, cost_rub=37.7, source_count=8, notes="test",
            ),
        )

    monkeypatch.setattr(auto_dr_mod, "submit_async_research", _fake_submit)
    monkeypatch.setattr(auto_dr_mod, "try_collect_async_research", _fake_poll)

    client = _authed_client()
    sid = client.post(
        "/api/v4/sessions", json={"question": "test research async flow"}
    ).json()["session_id"]
    client.post(
        f"/api/v4/sessions/{sid}/auto-dr",
        json={"service": "valyu", "mode": "standard", "prompt": "x"},
    )
    r = client.get(f"/api/v4/sessions/{sid}/auto-dr-status?task_id=t2")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["state"] == "completed"
    assert body["filename"] == "valyu_research_standard_t2.md"
    assert body["source_count"] == 8

    # Source appended, job removed from pending
    sess = client.get(f"/api/v4/sessions/{sid}").json()
    assert len(sess["source_reports"]) == 1
    assert sess["source_reports"][0]["filename"] == "valyu_research_standard_t2.md"
    assert sess["pending_dr_jobs"] == []


def test_auto_dr_cancel_openai_soft_cancel_when_no_live_task(monkeypatch):
    """After container restart there's no live asyncio.Task, but the
    endpoint must still clean the pending_dr_jobs entry (soft cancel).
    Old behaviour returned 410; new behaviour returns 200 with kind=soft."""
    from smart_report.sources import auto_dr as auto_dr_mod

    async def _fake_submit(service, question, *, mode="standard", session_id=None, store=None):
        return auto_dr_mod.AsyncResearchSubmission(
            task_id="oai-cancel-test", service="openai", mode="mini",
            cost_usd=0.50, eta_min_low=5, eta_min_high=10,
        )

    monkeypatch.setattr(auto_dr_mod, "submit_async_research", _fake_submit)

    client = _authed_client()
    sid = client.post(
        "/api/v4/sessions", json={"question": "openai cancel test"}
    ).json()["session_id"]
    client.post(
        f"/api/v4/sessions/{sid}/auto-dr",
        json={"service": "openai", "mode": "mini", "prompt": "x"},
    )
    r = client.post(f"/api/v4/sessions/{sid}/auto-dr-cancel?task_id=oai-cancel-test")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["state"] == "cancelled"
    assert body["kind"] == "soft"  # no live task → soft
    # pending_dr_jobs entry removed
    sess = client.get(f"/api/v4/sessions/{sid}").json()
    assert all(j.get("task_id") != "oai-cancel-test" for j in (sess.get("pending_dr_jobs") or []))


def test_auto_dr_cancel_tavily_is_soft_cancel(monkeypatch):
    """Tavily SDK has no cancel method — endpoint returns 200 with kind=soft."""
    from smart_report.sources import auto_dr as auto_dr_mod

    async def _fake_submit(service, question, *, mode="standard", session_id=None, store=None):
        return auto_dr_mod.AsyncResearchSubmission(
            task_id="tav-cancel-test", service="tavily", mode="mini",
            cost_usd=0.05, eta_min_low=2, eta_min_high=5,
        )

    monkeypatch.setattr(auto_dr_mod, "submit_async_research", _fake_submit)

    client = _authed_client()
    sid = client.post(
        "/api/v4/sessions", json={"question": "tavily soft cancel"}
    ).json()["session_id"]
    client.post(
        f"/api/v4/sessions/{sid}/auto-dr",
        json={"service": "tavily", "mode": "mini", "prompt": "x"},
    )
    r = client.post(f"/api/v4/sessions/{sid}/auto-dr-cancel?task_id=tav-cancel-test")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["state"] == "cancelled"
    assert body["kind"] == "soft"
    sess = client.get(f"/api/v4/sessions/{sid}").json()
    assert all(j.get("task_id") != "tav-cancel-test" for j in (sess.get("pending_dr_jobs") or []))


def test_auto_dr_cancel_valyu_attempts_hard_cancel(monkeypatch):
    """Valyu wrapper attempts SDK cancel — falls back to soft if it raises.
    Without VALYU_API_KEY in test env, the call is skipped and we get soft."""
    import os
    from smart_report.sources import auto_dr as auto_dr_mod

    async def _fake_submit(service, question, *, mode="standard", session_id=None, store=None):
        return auto_dr_mod.AsyncResearchSubmission(
            task_id="valyu-cancel-test", service="valyu", mode="standard",
            cost_usd=0.50, eta_min_low=10, eta_min_high=20,
        )

    monkeypatch.setattr(auto_dr_mod, "submit_async_research", _fake_submit)
    monkeypatch.delenv("VALYU_API_KEY", raising=False)  # force soft-cancel path

    client = _authed_client()
    sid = client.post(
        "/api/v4/sessions", json={"question": "valyu cancel test"}
    ).json()["session_id"]
    client.post(
        f"/api/v4/sessions/{sid}/auto-dr",
        json={"service": "valyu", "mode": "standard", "prompt": "x"},
    )
    r = client.post(f"/api/v4/sessions/{sid}/auto-dr-cancel?task_id=valyu-cancel-test")
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "cancelled"
    # Without API key, soft-cancel; with key it'd be hard.
    assert r.json()["kind"] == "soft"


def test_auto_dr_accept_partial_promotes_to_source_reports(monkeypatch):
    """When LLM DR was interrupted with partial content, accepting it
    moves partial_content to source_reports and removes the job entry."""
    from smart_report.sources import auto_dr as auto_dr_mod

    async def _fake_submit(service, question, *, mode="standard", session_id=None, store=None):
        return auto_dr_mod.AsyncResearchSubmission(
            task_id="oai-partial", service="openai", mode="mini",
            cost_usd=0.50, eta_min_low=5, eta_min_high=10,
        )

    monkeypatch.setattr(auto_dr_mod, "submit_async_research", _fake_submit)

    client = _authed_client()
    sid = client.post(
        "/api/v4/sessions", json={"question": "partial accept test"}
    ).json()["session_id"]
    client.post(
        f"/api/v4/sessions/{sid}/auto-dr",
        json={"service": "openai", "mode": "mini", "prompt": "x"},
    )
    # Simulate the streaming runner having flushed some partial content,
    # then the container being killed → state=interrupted_with_partial
    from smart_report.api import v4_endpoints as v4
    s = v4._store.get(sid)
    for j in s.pending_dr_jobs:
        if j["task_id"] == "oai-partial":
            j["partial_content"] = "# Partial DR result\n\nSome findings so far"
            j["partial_chars"] = 41
            j["state"] = "interrupted_with_partial"
    v4._store.update(s)

    r = client.post(f"/api/v4/sessions/{sid}/auto-dr-accept-partial?task_id=oai-partial")
    assert r.status_code == 200, r.text

    sess = client.get(f"/api/v4/sessions/{sid}").json()
    # source_reports has the partial as an upload, with _partial suffix
    assert any(
        u["filename"] == "auto_dr_openai_oai-part_partial.md"
        for u in sess["source_reports"]
    )
    # Job removed from pending_dr_jobs
    assert all(j["task_id"] != "oai-partial" for j in (sess.get("pending_dr_jobs") or []))


def test_auto_dr_accept_partial_404_when_no_partial():
    client = _authed_client()
    sid = client.post(
        "/api/v4/sessions", json={"question": "test"}
    ).json()["session_id"]
    r = client.post(f"/api/v4/sessions/{sid}/auto-dr-accept-partial?task_id=ghost")
    assert r.status_code == 404


def test_auto_dr_cancel_404_for_unknown_task():
    client = _authed_client()
    sid = client.post(
        "/api/v4/sessions", json={"question": "cancel 404 test"}
    ).json()["session_id"]
    r = client.post(f"/api/v4/sessions/{sid}/auto-dr-cancel?task_id=neverexisted")
    assert r.status_code == 404


def test_auto_dr_status_404_for_unknown_task():
    client = _authed_client()
    sid = client.post(
        "/api/v4/sessions", json={"question": "test research async flow"}
    ).json()["session_id"]
    r = client.get(f"/api/v4/sessions/{sid}/auto-dr-status?task_id=neverexisted")
    assert r.status_code == 404


def test_track_b_endpoints_are_wired():
    """Track B has shipped — analyze/synthesize/upload routes exist (body behaviour
    is covered by test_v4_full_cycle / test_analyzer / test_synthesizer)."""
    client = _authed_client()
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


def test_long_task_status_404_for_unknown_task():
    """Polling with a bogus task_id returns 404, not silent fallthrough."""
    client = _authed_client()
    sid = client.post(
        "/api/v4/sessions", json={"question": "long-task 404 test"}
    ).json()["session_id"]
    r = client.get(
        f"/api/v4/sessions/{sid}/long-task-status",
        params={"task_id": "neverexisted"},
    )
    assert r.status_code == 404


def test_concurrent_analyze_rejected_with_409(monkeypatch):
    """Submitting /analyze twice while one is in flight returns 409."""
    from smart_report import analyzer as analyzer_module
    from smart_report import intake as intake_module
    from smart_report import prompt_master as pm_module

    # Stall the analyzer LLM so the first task stays "running" while we
    # fire the second submission.
    import asyncio as _asyncio

    async def _slow_analyzer(*a, **kw):
        await _asyncio.sleep(2.0)  # long enough for second POST to arrive
        return LLMResult(
            text=json.dumps(
                {
                    "consensus": [],
                    "conflicts": [],
                    "gaps": [],
                    "followup_prompts": [],
                    "all_numeric_facts": [],
                    "all_qualitative_facts": [],
                    "high_relevance_facts": [],
                    "fact_coverage_target": 0,
                },
                ensure_ascii=False,
            ),
            cost_rub=0.0,
        )

    async def _intake_stub(*a, **kw):
        return LLMResult(
            text=json.dumps({"numeric_facts": [], "qualitative_facts": [], "claims": []}),
            cost_rub=0.0,
        )

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
            cost_rub=0.0,
        )

    monkeypatch.setattr(analyzer_module, "call_json", _slow_analyzer)
    monkeypatch.setattr(intake_module, "call_json", _intake_stub)
    monkeypatch.setattr(pm_module, "call_json", _pm_stub)

    client = _authed_client()
    sid = client.post(
        "/api/v4/sessions", json={"question": "concurrent test"}
    ).json()["session_id"]
    client.post(f"/api/v4/sessions/{sid}/generate-prompt")
    client.post(
        f"/api/v4/sessions/{sid}/upload-reports",
        files=[("files", ("a.md", b"# report a", "text/markdown"))],
    )

    r1 = client.post(f"/api/v4/sessions/{sid}/analyze")
    assert r1.status_code == 202, r1.text
    task_id_1 = r1.json()["task_id"]

    r2 = client.post(f"/api/v4/sessions/{sid}/analyze")
    assert r2.status_code == 409, r2.text
    assert task_id_1 in r2.json()["detail"]

    # Drain the first task so module-level state is clean for the next test.
    _await_long_task(client, sid, task_id_1, timeout=5.0)
