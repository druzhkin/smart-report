"""Tests for the Gamma PPTX exporter input-text builder + endpoint wiring.

The HTTP layer is tested with the GAMMA_API_KEY mock-failure path so we
exercise the long-task → failed verdict flow without making real Gamma
API calls. The build_input_text path is exercised on a realistic
FinalReport fixture to confirm tables/charts/callouts surface as
explicit data Gamma can pattern-match into slides.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from smart_report.api import app
from smart_report.api import v4_endpoints as v4
from smart_report.exporters.gamma_pptx import build_input_text
from smart_report.llm import LLMResult
from smart_report.models import (
    CalloutBlock,
    ChartSpec,
    ExecutiveSummaryV4,
    FinalReport,
    KeyNumberHighlight,
    QAItem,
    RankingItem,
    Source,
    Table,
    V4Session,
)


# ---------------------------------------------------------------------------
# build_input_text
# ---------------------------------------------------------------------------


def _make_realistic_final_report() -> FinalReport:
    """A FinalReport with every structured field populated.

    Mirrors the shape of a real synthesizer output so the input_text
    builder is exercised on data-density similar to production. This is
    the same shape that should hit Gamma's API — i.e. the test catches
    regressions where new structured fields land in the schema but the
    builder forgets to surface them.
    """
    return FinalReport(
        session_id="fixture-gamma-001",
        question="Какие amenities дают максимальную ценовую премию?",
        research_prompt_used="Q",
        executive_summary=ExecutiveSummaryV4(
            main_answer="МОПы и закрытая территория дают +8–15% к цене.",
            top_findings=[
                "Закрытая территория: +7–12% к цене [ЕРЗ]",
                "МОПы класса отель: +8–15% к цене [Knight Frank]",
            ],
            key_numbers=[],
            confidence_note="medium",
            what_meta_adds="reconciled премии fitness 3% / 5% / 8%",
        ),
        main_synthesis="## Позиция\n\nТоп-3: closed yard, lobby, фитнес.",
        consensus_section="Все три источника согласны по топ-3.",
        conflicts_section="ЕРЗ 55% vs Knight Frank 68% по ипотеке.",
        gaps_filled_section="open: данные по NPS застройщиков.",
        all_sources=[
            Source(title="ЕРЗ", url="https://erzrf.ru/", tool="perplexity", reliability="high"),
            Source(title="Knight Frank", url="https://knightfrank.ru/", tool="claude", reliability="medium"),
        ],
        metadata={},
        qa_section=[
            QAItem(
                question="Что важнее всего?",
                answer="Closed yard + lobby отель-класса.",
                details_ref="Раздел 1",
            ),
        ],
        ranking=[
            RankingItem(label="closed yard", weight=25, rationale="высшая премия", evidence_strength="high"),
            RankingItem(label="lobby отель", weight=22, rationale="первое впечатление", evidence_strength="high"),
            RankingItem(label="фитнес", weight=18, rationale="ROI ср.", evidence_strength="medium"),
        ],
        tables=[
            Table(
                title="Amenities ROI",
                columns=["Amenity", "Премия", "CAPEX"],
                rows=[
                    ["closed yard", "+9.5%", "0.5–1%"],
                    ["lobby отель", "+11.5%", "2–3%"],
                    ["фитнес", "+4%", "1–2%"],
                ],
                caption="Москва бизнес 2024",
                source_ref="ЕРЗ + Knight Frank",
            ),
        ],
        charts=[
            ChartSpec(
                chart_type="bar",
                title="Премия от amenities",
                data={"labels": ["yard", "lobby", "fitness"], "values": [9.5, 11.5, 4.0]},
                x_label="Amenity",
                y_label="Премия %",
                caption="средние диапазоны",
            ),
        ],
        callouts=[
            CalloutBlock(
                kind="insight",
                title="Закон убывающей отдачи",
                body="После 7-8 amenities каждая следующая <1%.",
            ),
            CalloutBlock(
                kind="warning",
                title="Бассейн — ловушка",
                body="CAPEX 3-5% при +2-4% премии.",
            ),
        ],
        key_numbers_highlight=[
            KeyNumberHighlight(
                value="+8-15%",
                label="премия от lobby отель-класса",
                source_ref="Knight Frank",
                importance="headline",
            ),
            KeyNumberHighlight(
                value="3-5%",
                label="оптимальный CAPEX на amenities",
                source_ref="Analyzer synthesis",
                importance="primary",
            ),
        ],
    )


def test_build_input_text_includes_all_structured_fields():
    report = _make_realistic_final_report()
    text = build_input_text(report)

    # Title + main answer
    assert "amenities" in text.lower()
    assert "+8–15%" in text or "+8-15%" in text  # main_answer might use either dash

    # Top findings
    assert "Закрытая территория" in text
    assert "Knight Frank" in text

    # KPI table from key_numbers_highlight
    assert "Headline KPI" in text
    assert "премия от lobby отель-класса" in text
    assert "+8-15%" in text

    # Q&A section
    assert "Что важнее всего" in text
    assert "Closed yard + lobby отель-класса" in text

    # Ranking table
    assert "Приоритизация" in text
    assert "closed yard" in text
    assert "lobby отель" in text
    assert "25" in text  # weight column

    # Custom tables
    assert "Amenities ROI" in text
    assert "+9.5%" in text and "+11.5%" in text

    # Charts — explicit chart type + data points
    assert "Премия от amenities" in text
    assert "**bar**" in text  # chart type hint surfaced for Gamma
    assert "9.5" in text and "11.5" in text

    # Callouts — both kinds
    assert "💡" in text  # insight emoji
    assert "⚠️" in text  # warning emoji
    assert "Закон убывающей отдачи" in text
    assert "Бассейн — ловушка" in text

    # Sources at the tail
    assert "https://erzrf.ru/" in text
    assert "https://knightfrank.ru/" in text


def test_build_input_text_handles_empty_arrays():
    """Bare-bones report (no callouts/charts/tables) still renders without crashing."""
    report = FinalReport(
        session_id="empty",
        question="Q?",
        research_prompt_used="",
        executive_summary=ExecutiveSummaryV4(
            main_answer="A.",
            top_findings=[],
            key_numbers=[],
            confidence_note="",
            what_meta_adds="",
        ),
        main_synthesis="just prose",
        consensus_section="",
        conflicts_section="",
        gaps_filled_section="",
        all_sources=[],
        metadata={},
    )
    text = build_input_text(report)
    assert "# Q?" in text
    assert "A." in text
    assert "just prose" in text
    # No table/chart/callout markers should leak when arrays are empty
    assert "Headline KPI" not in text
    assert "Приоритизация" not in text


def test_build_input_text_truncates_huge_input():
    """Gamma cap is ~100k tokens (~400k chars). Builder caps at 350k +
    suffix so additionalInstructions still fits."""
    huge_synth = "x" * 500_000
    report = FinalReport(
        session_id="huge",
        question="Q",
        research_prompt_used="",
        executive_summary=ExecutiveSummaryV4(
            main_answer="",
            top_findings=[],
            key_numbers=[],
            confidence_note="",
            what_meta_adds="",
        ),
        main_synthesis=huge_synth,
        consensus_section="",
        conflicts_section="",
        gaps_filled_section="",
        all_sources=[],
        metadata={},
    )
    text = build_input_text(report)
    assert len(text) <= 350_100  # cap + truncation note
    assert "input truncated" in text


# ---------------------------------------------------------------------------
# Endpoint wiring — exercises long-task pattern + Gamma error path
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_state(tmp_path, monkeypatch):
    v4._V4_SESSIONS.clear()
    v4._V4_EVENTS.clear()
    v4._V4_EVENT_SIGNALS.clear()
    v4._LONG_TASK_REGISTRY.clear()
    from smart_report.api import auth as auth_module
    monkeypatch.setattr(auth_module, "_DATA_DIR", tmp_path / "auth")
    monkeypatch.setattr(auth_module, "_USERS_PATH", tmp_path / "auth" / "users.json")
    auth_module._SIGNUP_RATE.clear()
    yield
    v4._V4_SESSIONS.clear()
    v4._V4_EVENTS.clear()
    v4._V4_EVENT_SIGNALS.clear()


def _authed_client():
    c = TestClient(app)
    r = c.post(
        "/api/auth/signup",
        json={"email": "tester@example.com", "password": "test1234"},
    )
    assert r.status_code == 201, r.text
    return c


def _seed_session_with_final_report(monkeypatch) -> tuple[TestClient, str]:
    """Drive a session through prompt → upload → analyze → synthesize so it
    has a final_report ready for Gamma export."""
    from smart_report import analyzer as analyzer_module
    from smart_report import intake as intake_module
    from smart_report import prompt_master as pm_module
    from smart_report import synthesis_critic as critic_module
    from smart_report import synthesizer as synth_module

    pm_payload = {
        "full_prompt": "X" * 250,
        "reasoning": "r",
        "expected_structure": ["s"],
        "key_entities": ["PIK"],
        "tips_for_search": "Perplexity",
    }
    analyzer_payload = {
        "consensus": [], "conflicts": [], "gaps": [], "followup_prompts": [],
        "all_numeric_facts": [], "all_qualitative_facts": [],
        "high_relevance_facts": [], "fact_coverage_target": 0,
    }
    synth_payload = {
        "session_id": "ignored", "question": "Q", "research_prompt_used": "R",
        "executive_summary": {
            "main_answer": "A.", "top_findings": [], "key_numbers": [],
            "confidence_note": "", "what_meta_adds": "",
        },
        "main_synthesis": "S.", "consensus_section": "",
        "conflicts_section": "", "gaps_filled_section": "",
        "all_sources": [], "metadata": {},
    }

    async def _stub_pm(*a, **kw):
        return LLMResult(text=json.dumps(pm_payload), cost_rub=0.0)
    async def _stub_an(*a, **kw):
        return LLMResult(text=json.dumps(analyzer_payload), cost_rub=0.0)
    async def _stub_syn(*a, **kw):
        return LLMResult(text=json.dumps(synth_payload), cost_rub=0.0)
    async def _stub_intake(*a, **kw):
        return LLMResult(text=json.dumps({"numeric_facts": [], "qualitative_facts": [], "claims": []}), cost_rub=0.0)
    async def _stub_critic(*a, **kw):
        return LLMResult(
            text=json.dumps({"issues": [], "severity_summary": {"critical": 0, "material": 0, "minor": 0}, "overall_verdict": "pass"}),
            cost_rub=0.0,
        )

    monkeypatch.setattr(pm_module, "call_json", _stub_pm)
    monkeypatch.setattr(analyzer_module, "call_json", _stub_an)
    monkeypatch.setattr(synth_module, "call_json", _stub_syn)
    monkeypatch.setattr(intake_module, "call_json", _stub_intake)
    monkeypatch.setattr(critic_module, "call_json", _stub_critic)

    c = _authed_client()
    sid = c.post("/api/v4/sessions", json={"question": "test gamma"}).json()["session_id"]
    c.post(f"/api/v4/sessions/{sid}/generate-prompt")
    c.post(
        f"/api/v4/sessions/{sid}/upload-reports",
        files=[("files", ("a.md", b"# a", "text/markdown"))],
    )

    # Drive analyze + synthesize through the long-task pattern
    import time
    r = c.post(f"/api/v4/sessions/{sid}/analyze")
    assert r.status_code == 202, r.text
    tid = r.json()["task_id"]
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        s = c.get(f"/api/v4/sessions/{sid}/long-task-status", params={"task_id": tid}).json()
        if s["state"] in ("completed", "failed"):
            break
        time.sleep(0.02)
    assert s["state"] == "completed", s

    r = c.post(f"/api/v4/sessions/{sid}/synthesize")
    assert r.status_code == 202, r.text
    tid = r.json()["task_id"]
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        s = c.get(f"/api/v4/sessions/{sid}/long-task-status", params={"task_id": tid}).json()
        if s["state"] in ("completed", "failed"):
            break
        time.sleep(0.02)
    assert s["state"] == "completed", s

    return c, sid


def test_export_gamma_pptx_409_when_no_final_report():
    """Cannot export PPTX from a session that hasn't been synthesised yet."""
    client = _authed_client()
    sid = client.post(
        "/api/v4/sessions", json={"question": "no final report yet"}
    ).json()["session_id"]
    r = client.post(f"/api/v4/sessions/{sid}/export-gamma-pptx")
    assert r.status_code == 409


def test_export_gamma_pptx_records_failure_when_api_key_missing(monkeypatch):
    """No GAMMA_API_KEY → task starts (202), then fails fast in the
    background loop with a clear error in long-task-status."""
    monkeypatch.delenv("GAMMA_API_KEY", raising=False)
    client, sid = _seed_session_with_final_report(monkeypatch)

    r = client.post(f"/api/v4/sessions/{sid}/export-gamma-pptx")
    assert r.status_code == 202, r.text
    tid = r.json()["task_id"]
    assert r.json()["phase"] == "export-pptx"

    import time
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        s = client.get(
            f"/api/v4/sessions/{sid}/long-task-status",
            params={"task_id": tid},
        ).json()
        if s["state"] in ("completed", "failed"):
            break
        time.sleep(0.02)
    assert s["state"] == "failed", s
    assert "GAMMA_API_KEY" in (s["error"] or "")


def test_export_gamma_pptx_real_404_before_generation(monkeypatch):
    """GET /export?format=gamma-pptx-real returns a friendly 404 with hint
    when the file hasn't been produced yet."""
    client, sid = _seed_session_with_final_report(monkeypatch)
    r = client.get(
        f"/api/v4/sessions/{sid}/export",
        params={"format": "gamma-pptx-real"},
    )
    assert r.status_code == 404
    assert "export-gamma-pptx" in r.text
