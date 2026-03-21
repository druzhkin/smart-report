"""Tests for FastAPI REST endpoints."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.main import app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def created_session(client):
    """Create a session and return its ID, suppressing the background pipeline."""
    with patch("backend.api.routes.reports._run_pipeline", new_callable=AsyncMock):
        resp = client.post(
            "/api/reports",
            json={"request": "AI market analysis", "depth": "light", "output_formats": ["pdf"]},
        )
    assert resp.status_code == 200
    return resp.json()["session_id"]


# ---------------------------------------------------------------------------
# POST /api/reports
# ---------------------------------------------------------------------------


class TestCreateReport:
    def test_returns_session_id(self, client):
        with patch("backend.api.routes.reports._run_pipeline", new_callable=AsyncMock):
            resp = client.post(
                "/api/reports",
                json={"request": "AI market analysis", "depth": "light", "output_formats": ["pdf"]},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "session_id" in data
        assert isinstance(data["session_id"], str)
        assert len(data["session_id"]) == 36  # UUID format

    def test_estimated_time_light(self, client):
        with patch("backend.api.routes.reports._run_pipeline", new_callable=AsyncMock):
            resp = client.post("/api/reports", json={"request": "Test", "depth": "light"})
        assert resp.json()["estimated_time_minutes"] == 3

    def test_estimated_time_standard_default(self, client):
        with patch("backend.api.routes.reports._run_pipeline", new_callable=AsyncMock):
            resp = client.post("/api/reports", json={"request": "Test"})
        assert resp.json()["estimated_time_minutes"] == 8

    def test_estimated_time_deep(self, client):
        with patch("backend.api.routes.reports._run_pipeline", new_callable=AsyncMock):
            resp = client.post("/api/reports", json={"request": "Test", "depth": "deep"})
        assert resp.json()["estimated_time_minutes"] == 15

    def test_estimated_time_exhaustive(self, client):
        with patch("backend.api.routes.reports._run_pipeline", new_callable=AsyncMock):
            resp = client.post("/api/reports", json={"request": "Test", "depth": "exhaustive"})
        assert resp.json()["estimated_time_minutes"] == 30

    def test_unique_session_ids(self, client):
        ids = []
        for _ in range(3):
            with patch("backend.api.routes.reports._run_pipeline", new_callable=AsyncMock):
                resp = client.post("/api/reports", json={"request": "Test"})
            ids.append(resp.json()["session_id"])
        assert len(set(ids)) == 3  # all unique


# ---------------------------------------------------------------------------
# GET /api/reports/{id}
# ---------------------------------------------------------------------------


class TestGetReport:
    def test_get_existing_session(self, client, created_session):
        resp = client.get(f"/api/reports/{created_session}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == created_session
        assert "status" in data
        assert "cost_usd" in data
        assert "report_urls" in data

    def test_get_unknown_session_returns_404(self, client):
        resp = client.get("/api/reports/nonexistent-00000000")
        assert resp.status_code == 404

    def test_initial_status_not_failed(self, client, created_session):
        resp = client.get(f"/api/reports/{created_session}")
        assert resp.json()["status"] != "failed"

    def test_report_field_none_initially(self, client, created_session):
        resp = client.get(f"/api/reports/{created_session}")
        # Report is None until pipeline completes
        assert resp.json()["report"] is None


# ---------------------------------------------------------------------------
# GET /api/reports/{id}/stream (SSE)
# ---------------------------------------------------------------------------


class TestSSEStream:
    def test_unknown_session_returns_404(self, client):
        resp = client.get("/api/reports/bad-session-id/stream")
        assert resp.status_code == 404

    def test_stream_returns_sse_content_type(self, client, created_session):
        from backend.api.routes import reports as routes_module

        # Mark session as completed so generator terminates immediately
        routes_module._sessions[created_session].status = "completed"

        resp = client.get(
            f"/api/reports/{created_session}/stream",
            headers={"Accept": "text/event-stream"},
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")

    def test_stream_replays_buffered_events(self, client):
        from backend.api.routes import reports as routes_module

        with patch("backend.api.routes.reports._run_pipeline", new_callable=AsyncMock):
            create_resp = client.post("/api/reports", json={"request": "Stream test"})
        session_id = create_resp.json()["session_id"]

        # Inject a buffered event and mark complete
        event = routes_module._make_event("intake", "done", "Intake complete", 0.01, 100)
        routes_module._session_events[session_id].append(event)
        routes_module._sessions[session_id].status = "completed"

        resp = client.get(f"/api/reports/{session_id}/stream")
        assert resp.status_code == 200
        assert "intake" in resp.text
        assert "done" in resp.text

    def test_stream_event_is_valid_json(self, client):
        from backend.api.routes import reports as routes_module

        with patch("backend.api.routes.reports._run_pipeline", new_callable=AsyncMock):
            create_resp = client.post("/api/reports", json={"request": "JSON test"})
        session_id = create_resp.json()["session_id"]

        event = routes_module._make_event("research", "started", "Research started", 0.05, 500)
        routes_module._session_events[session_id].append(event)
        routes_module._sessions[session_id].status = "completed"

        resp = client.get(f"/api/reports/{session_id}/stream")
        # Extract data lines and parse JSON
        for line in resp.text.splitlines():
            if line.startswith("data:"):
                payload = json.loads(line[len("data:"):].strip())
                assert "step" in payload
                assert "status" in payload
                assert "timestamp" in payload


# ---------------------------------------------------------------------------
# GET /api/reports/{id}/download/{format}
# ---------------------------------------------------------------------------


class TestDownloadEndpoint:
    def test_unknown_session_returns_404(self, client):
        resp = client.get("/api/reports/nonexistent/download/pdf")
        assert resp.status_code == 404

    def test_unsupported_format_returns_400(self, client, created_session):
        resp = client.get(f"/api/reports/{created_session}/download/xlsx")
        assert resp.status_code == 400

    def test_unsupported_format_csv_returns_400(self, client, created_session):
        resp = client.get(f"/api/reports/{created_session}/download/csv")
        assert resp.status_code == 400

    def test_missing_file_returns_404(self, client, created_session):
        # File doesn't exist on disk yet
        resp = client.get(f"/api/reports/{created_session}/download/pdf")
        assert resp.status_code == 404

    def test_pdf_download_returns_file(self, client, tmp_path, monkeypatch, created_session):
        from backend.config import settings

        monkeypatch.setattr(settings, "outputs_dir", str(tmp_path))

        fake_pdf = tmp_path / f"{created_session}.pdf"
        fake_pdf.write_bytes(b"%PDF-1.4 fake content")

        resp = client.get(f"/api/reports/{created_session}/download/pdf")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.content == b"%PDF-1.4 fake content"

    def test_docx_download_returns_file(self, client, tmp_path, monkeypatch, created_session):
        from backend.config import settings

        monkeypatch.setattr(settings, "outputs_dir", str(tmp_path))

        fake_docx = tmp_path / f"{created_session}.docx"
        fake_docx.write_bytes(b"PK fake docx content")

        resp = client.get(f"/api/reports/{created_session}/download/docx")
        assert resp.status_code == 200
        assert "wordprocessingml" in resp.headers["content-type"]

    def test_pptx_format_alias(self, client, tmp_path, monkeypatch, created_session):
        from backend.config import settings

        monkeypatch.setattr(settings, "outputs_dir", str(tmp_path))

        fake_pptx = tmp_path / f"{created_session}.pptx"
        fake_pptx.write_bytes(b"PK fake pptx content")

        resp = client.get(f"/api/reports/{created_session}/download/presentation")
        assert resp.status_code == 200
        assert "presentationml" in resp.headers["content-type"]


# ---------------------------------------------------------------------------
# POST /api/reports/{id}/feedback
# ---------------------------------------------------------------------------


class TestFeedback:
    def test_submit_feedback_ok(self, client, created_session):
        resp = client.post(
            f"/api/reports/{created_session}/feedback",
            json={"rating": 5, "comment": "Excellent report"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_feedback_unknown_session_404(self, client):
        resp = client.post(
            "/api/reports/nonexistent/feedback",
            json={"rating": 3, "comment": ""},
        )
        assert resp.status_code == 404

    def test_feedback_stored_in_session(self, client):
        from backend.api.routes import reports as routes_module

        with patch("backend.api.routes.reports._run_pipeline", new_callable=AsyncMock):
            create_resp = client.post("/api/reports", json={"request": "Feedback store test"})
        session_id = create_resp.json()["session_id"]

        client.post(
            f"/api/reports/{session_id}/feedback",
            json={"rating": 4, "comment": "Good"},
        )

        session = routes_module._sessions[session_id]
        assert session.feedback is not None
        assert session.feedback["rating"] == 4
        assert session.feedback["comment"] == "Good"


# ---------------------------------------------------------------------------
# GET /api/health
# ---------------------------------------------------------------------------


class TestHealth:
    def test_health_endpoint_exists(self, client):
        # Health check may fail external connections in test, but route should exist
        resp = client.get("/api/health")
        assert resp.status_code in (200, 503)  # 503 if external deps unreachable
