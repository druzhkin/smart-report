"""Landing + /app pages routing tests (post-SaaS pivot).

Landing is PUBLIC now (no admin/admin Basic auth). The /app HTML
shells are also public files; auth is enforced by the JS calling
/api/auth/me on load and the data API endpoints (/api/auth/*,
/api/reports/*) gating via session cookies.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from smart_report.api.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_landing_index_serves_html_publicly(client: TestClient):
    """Marketing page must be reachable without credentials — that's the
    point of a SaaS landing."""
    r = client.get("/landing/")
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")
    body = r.text
    assert "<!doctype html>" in body.lower() or "<!DOCTYPE html>" in body
    assert "landing.css" in body


def test_landing_serves_landing_css(client: TestClient):
    r = client.get("/landing/landing.css")
    assert r.status_code == 200
    assert "text/css" in r.headers.get("content-type", "")
    assert len(r.content) > 1000


def test_landing_serves_jsx_component(client: TestClient):
    r = client.get("/landing/landing_a_sales.jsx")
    assert r.status_code == 200
    assert len(r.content) > 100


def test_landing_path_traversal_blocked(client: TestClient):
    r = client.get("/landing/../README.md")
    assert r.status_code in (400, 404)


def test_landing_missing_file_404(client: TestClient):
    r = client.get("/landing/does-not-exist.html")
    assert r.status_code == 404


def test_health_endpoint(client: TestClient):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_root_redirects_to_landing_when_logged_out(client: TestClient):
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == "/landing/"


def test_favicon_returns_204_not_404(client: TestClient):
    r = client.get("/favicon.ico")
    assert r.status_code == 204


def test_app_signup_page_served(client: TestClient):
    r = client.get("/app/signup.html")
    assert r.status_code == 200
    assert "Регистрация" in r.text or "signup" in r.text.lower()


def test_app_login_page_served(client: TestClient):
    r = client.get("/app/login.html")
    assert r.status_code == 200
    assert "Вход" in r.text or "login" in r.text.lower()


def test_app_dashboard_page_served(client: TestClient):
    r = client.get("/app/dashboard.html")
    assert r.status_code == 200
    # Auth check is client-side; the page itself loads regardless
    assert "dashboard" in r.text.lower() or "Кабинет" in r.text or "Создать отчёт" in r.text


def test_app_default_serves_dashboard(client: TestClient):
    """GET /app/ (trailing slash) → dashboard.html."""
    r = client.get("/app/", follow_redirects=False)
    # Either 200 with dashboard content, or 307 redirect — both acceptable
    assert r.status_code in (200, 307)


def test_app_path_traversal_blocked(client: TestClient):
    r = client.get("/app/../README.md")
    assert r.status_code in (400, 404)


def test_app_css_served(client: TestClient):
    r = client.get("/app/app.css")
    assert r.status_code == 200
    assert "text/css" in r.headers.get("content-type", "")
