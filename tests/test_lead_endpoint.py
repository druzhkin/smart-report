"""Tests for POST /api/lead — landing form capture."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from smart_report.api.main import app
from smart_report.api import lead as lead_module


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def isolate_leads_dir(tmp_path, monkeypatch):
    """Redirect runs/leads/ → tmp so tests don't pollute the real dir."""
    fake_dir = tmp_path / "leads"
    monkeypatch.setattr(lead_module, "_LEADS_DIR", fake_dir)
    monkeypatch.setattr(lead_module, "_LEADS_JSONL", fake_dir / "leads.jsonl")
    return fake_dir


def test_lead_minimal_post_returns_201(client: TestClient, isolate_leads_dir: Path):
    r = client.post(
        "/api/lead",
        json={"package": "start", "email": "user@example.com"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["ok"] is True
    assert isinstance(body["id"], str) and len(body["id"]) == 12

    # leads.jsonl appended
    jsonl = isolate_leads_dir / "leads.jsonl"
    assert jsonl.exists()
    line = jsonl.read_text(encoding="utf-8").strip()
    rec = json.loads(line)
    assert rec["package"] == "start"
    assert rec["email"] == "user@example.com"
    assert rec["id"] == body["id"]
    assert "received_at" in rec


def test_lead_full_post_persists_all_fields(client: TestClient, isolate_leads_dir: Path):
    payload = {
        "package": "pack5",
        "package_title": "Pack 5 · ₽39 000 (5 отчётов)",
        "name": "Иван Петров",
        "email": "ivan@firm.ru",
        "message": "Нужны 5 отчётов по EV-рынку России до конца квартала",
        "source": "landing_a_sales",
    }
    r = client.post("/api/lead", json=payload)
    assert r.status_code == 201
    rec = json.loads((isolate_leads_dir / "leads.jsonl").read_text(encoding="utf-8").strip())
    for k, v in payload.items():
        assert rec[k] == v


def test_lead_rejects_invalid_email(client: TestClient):
    r = client.post("/api/lead", json={"email": "not-an-email"})
    assert r.status_code == 422


def test_lead_rejects_missing_email(client: TestClient):
    r = client.post("/api/lead", json={"package": "start"})
    assert r.status_code == 422


def test_lead_message_length_capped(client: TestClient):
    huge = "x" * 5000
    r = client.post(
        "/api/lead",
        json={"email": "u@x.com", "message": huge},
    )
    assert r.status_code == 422  # exceeds _MAX_MESSAGE_LEN


def test_lead_appends_multiple_records(client: TestClient, isolate_leads_dir: Path):
    for i in range(3):
        r = client.post("/api/lead", json={"email": f"u{i}@x.com", "package": "single"})
        assert r.status_code == 201
    lines = (isolate_leads_dir / "leads.jsonl").read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 3
    emails = sorted(json.loads(l)["email"] for l in lines)
    assert emails == ["u0@x.com", "u1@x.com", "u2@x.com"]
