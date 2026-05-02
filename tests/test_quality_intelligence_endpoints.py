from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from smart_report.api import v4_endpoints as v4ep
from smart_report.models import ExecutiveSummaryV4, FinalReport, Source, V4Session


@pytest.fixture
def client() -> TestClient:
    v4ep._V4_SESSIONS.clear()
    v4ep._V4_EVENTS.clear()
    v4ep._V4_EVENT_SIGNALS.clear()
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="test")
    app.include_router(v4ep.router)
    return TestClient(app)


def _seed_final_report() -> str:
    session_id = "quality-intel"
    report = FinalReport(
        session_id=session_id,
        question="EU AI Act regulatory impact on enterprise SaaS",
        executive_summary=ExecutiveSummaryV4(main_answer="The regulatory burden rises [1]."),
        main_synthesis="Long synthesis " * 120,
        all_sources=[
            Source(title="European Commission", url="https://ec.europa.eu/example", tool="tavily"),
            Source(title="EUR-Lex", url="https://eur-lex.europa.eu/example", tool="tavily"),
        ],
    )
    v4ep._V4_SESSIONS[session_id] = V4Session(
        session_id=session_id,
        raw_question=report.question,
        final_report=report,
        status="synthesized",
        created_at=datetime.now(UTC),
    )
    return session_id


def test_quality_intelligence_endpoints_return_review_contracts(client: TestClient):
    session_id = _seed_final_report()

    evidence = client.get(f"/api/v4/sessions/{session_id}/evidence-graph")
    policy = client.get(f"/api/v4/sessions/{session_id}/research-policy")
    page_plan = client.get(f"/api/v4/sessions/{session_id}/page-plan")
    benchmark = client.get(f"/api/v4/sessions/{session_id}/benchmark-eval")

    assert evidence.status_code == 200
    assert evidence.json()["summary"]["claim_count"] >= 1
    assert policy.status_code == 200
    assert policy.json()["domain"] == "eu_regulatory"
    assert page_plan.status_code == 200
    assert page_plan.json()["summary"]["page_count"] >= 1
    assert benchmark.status_code == 200
    assert "passed" in benchmark.json()
