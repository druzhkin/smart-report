"""Reports endpoint tests — auth gating, validation, list/get."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from smart_report.api.main import app
from smart_report.api import auth as auth_module
from smart_report.api import reports as reports_module


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def isolate_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(auth_module, "_DATA_DIR", tmp_path / "auth")
    monkeypatch.setattr(auth_module, "_USERS_PATH", tmp_path / "auth" / "users.json")
    monkeypatch.setattr(reports_module, "_REPORTS_ROOT", tmp_path / "reports")
    # Stub _kick_background so tests don't actually run the v4 cycle
    monkeypatch.setattr(reports_module, "_kick_background", lambda *a, **kw: None)
    # Reset signup rate-limit so multiple sequential test signups don't 429.
    auth_module._SIGNUP_RATE.clear()


def _signup(client: TestClient, email: str = "u@x.com", pw: str = "secret123") -> None:
    r = client.post("/api/auth/signup", json={"email": email, "password": pw})
    assert r.status_code == 201


def test_create_report_requires_auth(client: TestClient):
    r = client.post("/api/v4/reports", json={"question": "What is the meaning of life?"})
    assert r.status_code == 401


def test_list_reports_requires_auth(client: TestClient):
    r = client.get("/api/v4/reports")
    assert r.status_code == 401


def test_create_report_returns_queued(client: TestClient):
    _signup(client)
    r = client.post("/api/v4/reports", json={"question": "Tesla Q4 2024 earnings outlook"})
    assert r.status_code == 202
    data = r.json()
    assert data["status"] == "queued"
    assert data["question"] == "Tesla Q4 2024 earnings outlook"
    assert isinstance(data["id"], str) and len(data["id"]) == 12


def test_create_report_question_too_short_422(client: TestClient):
    _signup(client)
    r = client.post("/api/v4/reports", json={"question": "hi"})
    assert r.status_code == 422


def test_list_reports_empty_initially(client: TestClient):
    _signup(client)
    r = client.get("/api/v4/reports")
    assert r.status_code == 200
    assert r.json() == []


def test_list_reports_returns_created(client: TestClient):
    _signup(client)
    client.post("/api/v4/reports", json={"question": "Question one for analysis"})
    client.post("/api/v4/reports", json={"question": "Question two for analysis"})
    r = client.get("/api/v4/reports")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 2
    questions = {i["question"] for i in items}
    assert questions == {"Question one for analysis", "Question two for analysis"}


def test_get_report_returns_status(client: TestClient):
    _signup(client)
    create = client.post("/api/v4/reports", json={"question": "What is going on with X stuff"}).json()
    r = client.get(f"/api/v4/reports/{create['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == create["id"]
    assert r.json()["status"] == "queued"


def test_get_unknown_report_404(client: TestClient):
    _signup(client)
    r = client.get("/api/v4/reports/notarealid1234")
    assert r.status_code == 404


def test_get_report_other_user_isolated(client: TestClient, tmp_path: Path):
    """User A can't see user B's reports — separate dirs."""
    _signup(client, email="alice@x.com")
    create = client.post("/api/v4/reports", json={"question": "Alice's private query analysis"}).json()
    # Logout, signup as Bob
    client.post("/api/auth/logout")
    _signup(client, email="bob@x.com")
    # Bob can't see Alice's report
    r = client.get(f"/api/v4/reports/{create['id']}")
    assert r.status_code == 404
    # Bob's list is empty
    assert client.get("/api/v4/reports").json() == []


def test_uploads_capped_at_5(client: TestClient):
    _signup(client)
    too_many = [{"filename": f"f{i}.md", "content": "test"} for i in range(6)]
    r = client.post("/api/v4/reports", json={"question": "Question with too many uploads", "uploads": too_many})
    assert r.status_code == 422


def test_docx_404_when_not_rendered(client: TestClient):
    _signup(client)
    create = client.post("/api/v4/reports", json={"question": "Question without DOCX yet"}).json()
    # Background runner is stubbed so no DOCX appears
    r = client.get(f"/api/v4/reports/{create['id']}/docx")
    assert r.status_code == 404
