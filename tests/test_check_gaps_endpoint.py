"""Tests for the v4.5 Phase 2 Step 2.4 /check-gaps endpoint.

Mock-only — no LLM, no network. Iteration cap, sub_question routing,
and analyze-required guard are exercised through the FastAPI test client.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from smart_report.api import v4_endpoints as v4ep
from smart_report.llm import LLMResult
from smart_report.models import (
    AnalysisOutput,
    NumericFact,
    ResearchPrompt,
    SourceRef,
    SubQuestion,
    UploadedMarkdown,
    V4Session,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    """Fresh FastAPI app with the v4 router mounted, isolated state."""
    # Reset module-level state so tests don't leak between each other.
    v4ep._V4_SESSIONS.clear()
    v4ep._V4_EVENTS.clear()
    v4ep._V4_EVENT_SIGNALS.clear()
    app = FastAPI()
    app.include_router(v4ep.router)
    return TestClient(app)


def _seed_session(
    *,
    session_id: str = "test-sess",
    has_sub_questions: bool = True,
    has_analysis: bool = True,
    iterations: int = 0,
) -> V4Session:
    """Insert a session into the v4 store with controlled state."""
    sub_qs = []
    if has_sub_questions:
        sub_qs = [
            SubQuestion(
                id="sq1",
                text="Какие тренды цен на жильё бизнес-класса Москвы 2024?",
                rationale="r",
                suggested_sources=["market_data", "regulatory"],
            ),
            SubQuestion(
                id="sq2",
                text="Какие риски ставки ЦБ для застройщиков премиум-сегмента?",
                rationale="r",
                suggested_sources=["regulatory"],
            ),
        ]
    research_prompt = ResearchPrompt(
        full_prompt="Stub research prompt",
        reasoning="r",
        decomposition_method=("llm_planner" if has_sub_questions else "none"),
        sub_questions=sub_qs,
    )
    analysis = None
    if has_analysis:
        # Empty source pool → both sub_questions become critical gaps
        analysis = AnalysisOutput()

    sess = V4Session(
        session_id=session_id,
        raw_question="Стратегический вопрос с несколькими векторами на 2026?",
        research_prompt=research_prompt,
        source_reports=[
            UploadedMarkdown(filename="r.md", content="content", word_count=1)
        ],
        analysis=analysis,
        status="analyzed" if has_analysis else "created",
        created_at=datetime.now(timezone.utc),
        gap_check_iterations=iterations,
    )
    v4ep._V4_SESSIONS[session_id] = sess
    v4ep._V4_EVENTS[session_id] = []
    return sess


def _follow_up_stub(items):
    async def _stub(*a, **kw):
        return LLMResult(
            text=json.dumps({"follow_up_prompts": items}, ensure_ascii=False),
            cost_rub=0.0,
        )
    return _stub


# ---------------------------------------------------------------------------
# Spec acceptance cases
# ---------------------------------------------------------------------------


def test_first_iteration_returns_gaps_and_prompts(client):
    """Happy path: gaps detected + follow-up prompts generated."""
    _seed_session()
    follow_up_payload = [
        {
            "sub_question_id": "sq1",
            "prompt_text": "DR prompt for sq1",
            "suggested_dr_tool": "perplexity_dr",
            "rationale": "r",
        },
        {
            "sub_question_id": "sq2",
            "prompt_text": "DR prompt for sq2",
            "suggested_dr_tool": "perplexity_dr",
            "rationale": "r",
        },
    ]
    with patch(
        "smart_report.follow_up_prompter.call_json",
        new=_follow_up_stub(follow_up_payload),
    ):
        r = client.post("/api/v4/sessions/test-sess/check-gaps")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["iteration_number"] == 1
    assert body["can_iterate_more"] is True
    assert len(body["gaps"]) == 2  # both sub_questions have zero coverage
    assert body["gap_count_by_severity"]["critical"] == 2
    assert len(body["follow_up_prompts"]) == 2
    assert all(p["suggested_dr_tool"] == "perplexity_dr" for p in body["follow_up_prompts"])
    # Iteration counter persisted
    assert v4ep._V4_SESSIONS["test-sess"].gap_check_iterations == 1


def test_second_iteration_after_followup(client):
    """After one round, calling check-gaps again increments to 2 and
    returns can_iterate_more=False — the analyst's last chance.
    """
    _seed_session(iterations=1)  # already had one round
    with patch(
        "smart_report.follow_up_prompter.call_json",
        new=_follow_up_stub([
            {
                "sub_question_id": "sq1",
                "prompt_text": "second-round prompt",
                "suggested_dr_tool": "perplexity_dr",
            }
        ]),
    ):
        r = client.post("/api/v4/sessions/test-sess/check-gaps")
    assert r.status_code == 200
    body = r.json()
    assert body["iteration_number"] == 2
    assert body["can_iterate_more"] is False
    # Summary text mentions the iteration limit
    assert "последняя" in body["summary_for_analyst"].lower() or "2" in body["summary_for_analyst"]


def test_third_iteration_returns_results_but_blocked(client):
    """Beyond the cap, the endpoint still serves the latest gaps for
    transparency but flips can_iterate_more=False (stays False) so
    the analyst stops looping.
    """
    _seed_session(iterations=2)  # already at cap
    with patch(
        "smart_report.follow_up_prompter.call_json",
        new=_follow_up_stub([]),  # planner may return nothing on a stale state
    ):
        r = client.post("/api/v4/sessions/test-sess/check-gaps")
    assert r.status_code == 200
    body = r.json()
    assert body["iteration_number"] == 3
    assert body["can_iterate_more"] is False


def test_no_gaps_returns_empty_response(client):
    """Adequate evidence → empty gaps + empty follow-ups. Endpoint
    doesn't 4xx — it confirms the session is in good shape.
    """
    sess = _seed_session()
    # Populate analysis with two authoritative sources matching both sub_qs
    fact = NumericFact(
        fact_id=NumericFact.make_id("v1", "m", "s"),
        value="v1",
        metric="m",
        subject="s",
        sources=[
            SourceRef(
                url="https://rosstat.gov.ru/zhilyo-trendy-biznes-2024.pdf",
                title="Тренды цен жилья бизнес-класс Москва 2024",
                confidence="primary",
            ),
            SourceRef(
                url="https://erzrf.ru/zhilyo-biznes-trendy-moskva-2024",
                title="Тренды жилья бизнес Москва 2024",
                confidence="primary",
            ),
            SourceRef(
                url="https://cbr.ru/stavka-zastroyshchiki-premium-riski-2024.pdf",
                title="Ставка центрального банка риски застройщиков премиум-сегмента 2024",
                confidence="primary",
            ),
            SourceRef(
                url="https://minstroyrf.gov.ru/stavka-zastroyshchiki-premium-2024",
                title="Регулирование ставка застройщики премиум-сегмента 2024",
                confidence="primary",
            ),
        ],
    )
    sess.analysis = AnalysisOutput(all_numeric_facts=[fact])
    v4ep._V4_SESSIONS[sess.session_id] = sess

    r = client.post("/api/v4/sessions/test-sess/check-gaps")
    assert r.status_code == 200
    body = r.json()
    assert body["gaps"] == []
    assert body["follow_up_prompts"] == []
    assert "не обнаружено" in body["summary_for_analyst"]


def test_endpoint_requires_completed_analyze(client):
    """No analysis → 400 with explanatory message; iteration counter
    NOT incremented (the call was a no-op).
    """
    _seed_session(has_analysis=False)
    r = client.post("/api/v4/sessions/test-sess/check-gaps")
    assert r.status_code == 400
    assert "analyze" in r.json()["detail"].lower()
    assert v4ep._V4_SESSIONS["test-sess"].gap_check_iterations == 0


def test_session_without_sub_questions_returns_empty_gracefully(client):
    """RU RE template path / factual queries don't populate sub_questions.
    Endpoint should not 4xx; it should return empty gaps with a
    short explanatory summary.
    """
    _seed_session(has_sub_questions=False)
    r = client.post("/api/v4/sessions/test-sess/check-gaps")
    assert r.status_code == 200
    body = r.json()
    assert body["gaps"] == []
    assert body["follow_up_prompts"] == []
    assert "доменный шаблон" in body["summary_for_analyst"].lower() or "под-вопрос" in body["summary_for_analyst"].lower()
    # Iteration still counted (the call DID return a useful response)
    assert v4ep._V4_SESSIONS["test-sess"].gap_check_iterations == 1


def test_unknown_session_returns_404(client):
    """Sanity: standard 404 path."""
    r = client.post("/api/v4/sessions/nonexistent/check-gaps")
    assert r.status_code == 404
