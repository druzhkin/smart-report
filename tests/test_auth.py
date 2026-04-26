"""SaaS auth tests — signup, login, logout, /me."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from smart_report.api.main import app
from smart_report.api import auth as auth_module


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def isolate_users(tmp_path, monkeypatch):
    """Per-test users.json so signups don't bleed across tests."""
    fake = tmp_path / "users.json"
    monkeypatch.setattr(auth_module, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(auth_module, "_USERS_PATH", fake)
    return fake


def test_signup_creates_user_and_session(client: TestClient, isolate_users: Path):
    r = client.post("/api/auth/signup", json={"email": "ann@example.com", "password": "secret123"})
    assert r.status_code == 201
    assert r.json() == {"ok": True, "email": "ann@example.com"}
    # users.json now has the user
    import json
    users = json.loads(isolate_users.read_text(encoding="utf-8"))
    assert "ann@example.com" in users
    assert "password_hash" in users["ann@example.com"]
    # /me reflects the session
    me = client.get("/api/auth/me").json()
    assert me["authenticated"] is True
    assert me["email"] == "ann@example.com"


def test_signup_duplicate_email_409(client: TestClient):
    client.post("/api/auth/signup", json={"email": "x@y.com", "password": "secret123"})
    r = client.post("/api/auth/signup", json={"email": "x@y.com", "password": "another1"})
    assert r.status_code == 409


def test_signup_short_password_422(client: TestClient):
    r = client.post("/api/auth/signup", json={"email": "x@y.com", "password": "abc"})
    assert r.status_code == 422


def test_signup_invalid_email_422(client: TestClient):
    r = client.post("/api/auth/signup", json={"email": "not-an-email", "password": "secret123"})
    assert r.status_code == 422


def test_login_success_after_signup(client: TestClient):
    client.post("/api/auth/signup", json={"email": "u@v.com", "password": "secret123"})
    # Fresh client (no signup session) logs in
    fresh = TestClient(app)
    r = fresh.post("/api/auth/login", json={"email": "u@v.com", "password": "secret123"})
    assert r.status_code == 200
    me = fresh.get("/api/auth/me").json()
    assert me["authenticated"] is True


def test_login_wrong_password_401(client: TestClient):
    client.post("/api/auth/signup", json={"email": "u@v.com", "password": "secret123"})
    r = client.post("/api/auth/login", json={"email": "u@v.com", "password": "wrong-pass"})
    assert r.status_code == 401


def test_login_nonexistent_user_401(client: TestClient):
    r = client.post("/api/auth/login", json={"email": "ghost@x.com", "password": "secret123"})
    assert r.status_code == 401


def test_logout_clears_session(client: TestClient):
    client.post("/api/auth/signup", json={"email": "ann@x.com", "password": "secret123"})
    assert client.get("/api/auth/me").json()["authenticated"] is True
    r = client.post("/api/auth/logout")
    assert r.status_code == 200
    assert client.get("/api/auth/me").json()["authenticated"] is False


def test_me_anonymous_returns_authenticated_false(client: TestClient):
    r = client.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json() == {"authenticated": False, "email": None}


def test_email_normalized_to_lowercase(client: TestClient, isolate_users: Path):
    r = client.post("/api/auth/signup", json={"email": "Mixed.Case@X.com", "password": "secret123"})
    assert r.status_code == 201
    # Login with different case should work
    fresh = TestClient(app)
    r2 = fresh.post("/api/auth/login", json={"email": "MIXED.case@x.COM", "password": "secret123"})
    assert r2.status_code == 200
