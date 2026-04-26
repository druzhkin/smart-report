"""Tests for /landing route + admin/admin HTTP Basic auth."""

from __future__ import annotations

import base64

import pytest
from fastapi.testclient import TestClient

from smart_report.api.main import app


def _basic_auth_header(user: str, pw: str) -> dict[str, str]:
    token = base64.b64encode(f"{user}:{pw}".encode("ascii")).decode("ascii")
    return {"Authorization": f"Basic {token}"}


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_landing_index_requires_auth(client: TestClient):
    """No credentials → 401 + WWW-Authenticate Basic challenge."""
    r = client.get("/landing/")
    assert r.status_code == 401
    assert r.headers.get("WWW-Authenticate", "").lower().startswith("basic")


def test_landing_index_rejects_wrong_password(client: TestClient):
    r = client.get("/landing/", headers=_basic_auth_header("admin", "wrong"))
    assert r.status_code == 401


def test_landing_index_rejects_wrong_username(client: TestClient):
    r = client.get("/landing/", headers=_basic_auth_header("not-admin", "admin"))
    assert r.status_code == 401


def test_landing_index_serves_html_with_admin_admin(client: TestClient):
    r = client.get("/landing/", headers=_basic_auth_header("admin", "admin"))
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")
    # Sanity check that we got the React+Babel landing template
    body = r.text
    assert "<!doctype html>" in body.lower() or "<!DOCTYPE html>" in body
    assert "landing.css" in body  # references the bundled stylesheet


def test_landing_serves_landing_css(client: TestClient):
    r = client.get(
        "/landing/landing.css",
        headers=_basic_auth_header("admin", "admin"),
    )
    assert r.status_code == 200
    assert "text/css" in r.headers.get("content-type", "")
    assert len(r.content) > 1000  # actual CSS, not empty


def test_landing_serves_jsx_component(client: TestClient):
    r = client.get(
        "/landing/landing_a_sales.jsx",
        headers=_basic_auth_header("admin", "admin"),
    )
    assert r.status_code == 200
    assert len(r.content) > 100


def test_landing_path_traversal_blocked(client: TestClient):
    """`../` walks should NOT escape the landing/ root."""
    r = client.get(
        "/landing/../README.md",
        headers=_basic_auth_header("admin", "admin"),
    )
    # Either FastAPI normalises the path and 404s, or our _safe_path
    # rejects with 400. Both are acceptable — the README must NOT leak.
    assert r.status_code in (400, 404)


def test_landing_missing_file_404(client: TestClient):
    r = client.get(
        "/landing/does-not-exist.html",
        headers=_basic_auth_header("admin", "admin"),
    )
    assert r.status_code == 404


def test_other_routes_still_work_without_auth(client: TestClient):
    """Landing auth must NOT leak onto unrelated routes (regression check)."""
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_root_redirects_to_landing(client: TestClient):
    """Bare domain → /landing/ so users opening the deploy URL hit the
    auth-gated landing page directly instead of the FastAPI 404 JSON."""
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == "/landing/"


def test_favicon_returns_204_not_404(client: TestClient):
    """Browsers always probe /favicon.ico — silence the console 404 noise."""
    r = client.get("/favicon.ico")
    assert r.status_code == 204
