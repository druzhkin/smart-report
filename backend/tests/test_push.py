from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.schemas.report_schema import ReportOutput, ReportSection, ReportStatus


@pytest.fixture
def push_db_path() -> Path:
    root = Path(__file__).resolve().parents[1] / ".test-artifacts"
    root.mkdir(parents=True, exist_ok=True)
    return root / f"push-{uuid.uuid4()}.db"


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def created_session(client):
    with patch("backend.api.routes.reports._run_pipeline", new_callable=AsyncMock):
        resp = client.post(
            "/api/reports",
            json={"request": "Push notification test", "depth": "light", "output_formats": ["pdf"]},
        )
    assert resp.status_code == 200
    return resp.json()["session_id"]


@pytest.fixture
def sample_report() -> ReportOutput:
    return ReportOutput(
        title="AI Chips Report",
        executive_summary="Summary",
        sections=[ReportSection(title="Overview", content="Body", order=1, sources=[])],
        status=ReportStatus.COMPLETED,
    )


class TestPushSubscriptions:
    @pytest.mark.skip(reason="Legacy reports subscribe endpoint was removed from the supported v2 runtime.")
    @pytest.mark.asyncio
    async def test_subscribe_saves_to_db(self, client, created_session, push_db_path, monkeypatch):
        from backend.config import settings
        from backend.utils.push import get_push_subscription

        monkeypatch.setattr(settings, "postgres_url", f"sqlite+aiosqlite:///{push_db_path}")

        resp = client.post(
            f"/api/reports/{created_session}/subscribe",
            json={
                "endpoint": "https://push.example.test/subscription",
                "keys": {"p256dh": "test-p256dh", "auth": "test-auth"},
            },
        )

        assert resp.status_code == 200
        saved = await get_push_subscription(created_session)
        assert saved is not None
        assert saved["endpoint"] == "https://push.example.test/subscription"
        assert saved["keys"]["auth"] == "test-auth"


class TestQAPushNotifications:
    @pytest.mark.asyncio
    async def test_push_sent_on_pass_verdict(self, push_db_path, monkeypatch, sample_report):
        from backend.agents.qa_agent import run_qa
        from backend.config import settings
        from backend.utils.push import save_push_subscription

        monkeypatch.setattr(settings, "postgres_url", f"sqlite+aiosqlite:///{push_db_path}")
        monkeypatch.setattr(settings, "next_public_vapid_key", "public-key")
        monkeypatch.setattr(settings, "vapid_private_key", "private-key")

        await save_push_subscription(
            "push-session",
            {
                "endpoint": "https://push.example.test/subscription",
                "keys": {"p256dh": "test-p256dh", "auth": "test-auth"},
            },
        )

        state = {
            "session_id": "push-session",
            "report": sample_report,
            "chart_paths": [],
            "cost_usd": 0.0,
        }
        visual_resp = json.dumps({"score": 0.9, "issues": []})
        substance_resp = json.dumps({"score": 0.85, "citation_score": 0.8, "issues": []})

        async def run_inline(func, *args, **kwargs):
            return func(*args, **kwargs)

        with (
            patch("backend.agents.qa_agent._call_visual_qa", return_value=visual_resp),
            patch("backend.agents.qa_agent._call_substance_qa", return_value=substance_resp),
            patch("backend.utils.push.webpush") as webpush_mock,
            patch("backend.utils.push.asyncio.to_thread", side_effect=run_inline),
        ):
            result = await run_qa(state)

        assert result["qa_result"].verdict.value == "PASS"
        webpush_mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_push_if_not_subscribed(self, push_db_path, monkeypatch, sample_report):
        from backend.agents.qa_agent import run_qa
        from backend.config import settings

        monkeypatch.setattr(settings, "postgres_url", f"sqlite+aiosqlite:///{push_db_path}")
        monkeypatch.setattr(settings, "next_public_vapid_key", "public-key")
        monkeypatch.setattr(settings, "vapid_private_key", "private-key")

        state = {
            "session_id": "missing-subscription",
            "report": sample_report,
            "chart_paths": [],
            "cost_usd": 0.0,
        }
        visual_resp = json.dumps({"score": 0.9, "issues": []})
        substance_resp = json.dumps({"score": 0.85, "citation_score": 0.8, "issues": []})

        with (
            patch("backend.agents.qa_agent._call_visual_qa", return_value=visual_resp),
            patch("backend.agents.qa_agent._call_substance_qa", return_value=substance_resp),
            patch("backend.utils.push.webpush") as webpush_mock,
        ):
            result = await run_qa(state)

        assert result["qa_result"].verdict.value == "PASS"
        webpush_mock.assert_not_called()
