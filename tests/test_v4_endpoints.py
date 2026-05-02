"""v4 HTTP layer — /api/v4/sessions and /generate-prompt (LLM mocked)."""

from __future__ import annotations

import json
import zipfile
from io import BytesIO

import pytest

pytest.importorskip("fastapi")
httpx = pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from smart_report.api import app
from smart_report.api import v4_endpoints as v4
from smart_report.llm import LLMResult


_STUB = {
    "full_prompt": (
        "Goal: determine whether brand, speed, or product quality best explains "
        "commercial success for developers in Moscow's business-class segment "
        "between 2023 and 2025. Analyse the nine named developers (PIK, Donstroy, "
        "MR Group, Level Group, Etalon, Sminex, Capital Group, FSK, A101) across "
        "six structured sections with URL-cited figures from ERZ, bnMAP, and "
        "CIAN Pro. Forbid hedging — pick a driver and defend it."
    ),
    "reasoning": "Names 9 developers and 3 canonical data sources; demands a position.",
    "expected_structure": ["Scoring", "Brand", "Speed", "Product", "Correlation", "Limits"],
    "key_entities": ["PIK", "Donstroy", "MR Group", "ERZ"],
    "tips_for_search": "Perplexity DR for figures, OpenAI DR for narrative.",
}


@pytest.fixture(autouse=True)
def _reset_state(tmp_path, monkeypatch):
    v4._V4_SESSIONS.clear()
    v4._V4_EVENTS.clear()
    v4._V4_EVENT_SIGNALS.clear()
    # Per-user isolation + cost cap require an authenticated user. Isolate
    # the auth user store to a temp file per test and clear the in-memory
    # signup rate-limit so repeated tests don't 429 each other.
    from smart_report.api import auth as auth_module
    monkeypatch.setattr(auth_module, "_DATA_DIR", tmp_path / "auth")
    monkeypatch.setattr(auth_module, "_USERS_PATH", tmp_path / "auth" / "users.json")
    auth_module._SIGNUP_RATE.clear()
    yield
    v4._V4_SESSIONS.clear()
    v4._V4_EVENTS.clear()
    v4._V4_EVENT_SIGNALS.clear()


def _authed_client():
    """TestClient with a fresh signed-up user — sets the session cookie so
    POST /api/v4/sessions and the per-user-gated endpoints accept calls."""
    c = TestClient(app)
    r = c.post(
        "/api/auth/signup",
        json={"email": "tester@example.com", "password": "test1234"},
    )
    assert r.status_code == 201, r.text
    return c


def _await_long_task(client, sid: str, task_id: str, timeout: float = 5.0) -> dict:
    """Poll /long-task-status until terminal, return the final status body.

    Used by tests that submit /analyze or /synthesize and need the
    background asyncio.Task to finish before asserting on results.
    With LLM stubs the task usually completes within the first few
    polls; the timeout is a guardrail.
    """
    import time
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        r = client.get(
            f"/api/v4/sessions/{sid}/long-task-status",
            params={"task_id": task_id},
        )
        assert r.status_code == 200, r.text
        last = r.json()
        if last["state"] in ("completed", "failed"):
            return last
        time.sleep(0.02)
    raise AssertionError(
        f"long-task {task_id} did not reach terminal state in {timeout}s; "
        f"last poll: {last}"
    )


def test_artifact_qa_docx_page_count_prefers_rendered_pages():
    report = {
        "results": [
            {
                "kind": "docx",
                "metrics": {"estimated_pages": 7, "rendered_pages": 22},
            }
        ]
    }

    assert v4._artifact_qa_docx_page_count(report) == 22


def test_artifact_qa_docx_page_count_falls_back_to_estimate():
    report = {
        "results": [
            {
                "kind": "docx",
                "metrics": {"estimated_pages": 19},
            }
        ]
    }

    assert v4._artifact_qa_docx_page_count(report) == 19


@pytest.fixture
def mock_llm(monkeypatch):
    from smart_report import prompt_master as pm_module

    async def _stub(*args, **kwargs):
        return LLMResult(text=json.dumps(_STUB, ensure_ascii=False), cost_rub=0.0)

    monkeypatch.setattr(pm_module, "call_json", _stub)


def test_create_session_returns_session_id():
    client = _authed_client()
    r = client.post("/api/v4/sessions", json={"question": "what drives developer success"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "session_id" in body
    assert len(body["session_id"]) == 12


def test_create_session_rejects_short_question():
    client = _authed_client()
    r = client.post("/api/v4/sessions", json={"question": "hi"})
    assert r.status_code == 422


def test_generate_prompt_end_to_end(mock_llm):
    client = _authed_client()
    r = client.post("/api/v4/sessions", json={"question": "market analysis please"})
    sid = r.json()["session_id"]

    r2 = client.post(f"/api/v4/sessions/{sid}/generate-prompt")
    assert r2.status_code == 200, r2.text
    data = r2.json()
    assert data["full_prompt"].startswith("Goal:")
    assert len(data["full_prompt"]) > 200
    assert "PIK" in data["key_entities"]
    assert len(data["expected_structure"]) == 6


def test_generate_prompt_404_on_unknown_session():
    client = _authed_client()
    r = client.post("/api/v4/sessions/no-such-id/generate-prompt")
    assert r.status_code == 404


def test_generate_prompt_preserves_openrouter_402(monkeypatch):
    from smart_report import prompt_master as pm_module

    async def _fail_402(*args, **kwargs):
        request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
        response = httpx.Response(402, request=request, text="insufficient credits")
        raise httpx.HTTPStatusError("402 Payment Required", request=request, response=response)

    monkeypatch.setattr(pm_module, "call_json", _fail_402)
    client = _authed_client()
    sid = client.post("/api/v4/sessions", json={"question": "market analysis please"}).json()["session_id"]

    r = client.post(f"/api/v4/sessions/{sid}/generate-prompt")

    assert r.status_code == 402
    assert "OpenRouter credits" in r.json()["detail"]


def test_get_session_after_prompt_generation(mock_llm):
    client = _authed_client()
    sid = client.post("/api/v4/sessions", json={"question": "what drives it"}).json()["session_id"]
    client.post(f"/api/v4/sessions/{sid}/generate-prompt")
    r = client.get(f"/api/v4/sessions/{sid}")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "prompt_ready"
    assert body["research_prompt"] is not None
    assert body["research_prompt"]["full_prompt"].startswith("Goal:")


def test_events_route_returns_prompt_master_events(mock_llm):
    client = _authed_client()
    sid = client.post("/api/v4/sessions", json={"question": "what drives it"}).json()["session_id"]
    client.post(f"/api/v4/sessions/{sid}/generate-prompt")
    r = client.get(f"/api/v4/sessions/{sid}/events", params={"since": 0, "timeout": 0})
    assert r.status_code == 200
    body = r.json()
    phases = [e["phase"] for e in body["events"]]
    assert "prompt_master" in phases


def test_v4_full_cycle(monkeypatch, tmp_path):
    """upload-reports → analyze → synthesize → export?format=md, all LLMs mocked."""
    from smart_report import analyzer as analyzer_module
    from smart_report import prompt_master as pm_module
    from smart_report import synthesizer as synth_module

    analyzer_payload = {
        "per_source_summary": [
            {"source": "perplexity", "summary": "s1", "strengths": "", "weaknesses": ""}
        ],
        "consensus": [
            {"claim": "shared claim", "supporting_sources": ["perplexity", "openai_dr"], "confidence": "high"}
        ],
        "conflicts": [
            {
                "topic": "mortgage",
                "source_a": "perplexity",
                "claim_a": "55%",
                "source_b": "openai_dr",
                "claim_b": "68%",
                "resolution_hint": "cross-check ERZ",
                "importance": "critical",
            }
        ],
        "gaps": [
            {"topic": "delivery", "why_critical": "speed", "what_to_find": "%", "candidate_sources": ["erzrf.ru"]}
        ],
        "unverified_numbers": [],
        "quality_notes": "ok",
        "followup_prompts": [
            {
                "prompt_id": "fp_01",
                "intent": "fill_gap",
                "prompt": "Find delay % on erzrf.ru for PIK, Donstroy.",
                "target_info": "delay",
                "suggested_tool": "perplexity",
                "suggested_source_site": "erzrf.ru",
                "priority": "must",
                "linked_to": "gap:delivery",
            }
        ],
    }

    synth_payload = {
        "session_id": "ignored",
        "question": "Q",
        "research_prompt_used": "R",
        "executive_summary": {
            "main_answer": "Product > speed > brand.",
            "ranking": "Продукт > скорость > бренд",
            "top_findings": ["Top-5 47%", "Mortgage 55%"],
            "key_numbers": [{"value": "47%", "metric": "top-5 share", "subject": "2024", "source_url": ""}],
            "confidence_note": "medium",
            "what_meta_adds": "resolved mortgage-share skew",
        },
        "main_synthesis": "## Позиция\n\nПродукт > скорость > бренд.",
        "consensus_section": "all agree on top-3.",
        "conflicts_section": "55 vs 68 — pick 55.",
        "gaps_filled_section": "delivery open.",
        "all_sources": [
            {"title": "ERZ", "url": "https://erzrf.ru/", "tool": "perplexity", "reliability": "high"}
        ],
        "metadata": {},
    }

    async def _pm_stub(*a, **kw):
        return LLMResult(
            text=json.dumps(
                {
                    "full_prompt": "X" * 250,
                    "reasoning": "r",
                    "expected_structure": ["s1"],
                    "key_entities": ["PIK"],
                    "tips_for_search": "Perplexity",
                },
                ensure_ascii=False,
            ),
            cost_rub=0.12,
        )

    async def _an_stub(*a, **kw):
        return LLMResult(text=json.dumps(analyzer_payload, ensure_ascii=False), cost_rub=0.12)

    async def _syn_stub(*a, **kw):
        return LLMResult(text=json.dumps(synth_payload, ensure_ascii=False), cost_rub=0.12)

    async def _intake_stub(*a, **kw):
        return LLMResult(
            text=json.dumps({"numeric_facts": [], "qualitative_facts": [], "claims": []}),
            cost_rub=0.0,
        )

    async def _critic_stub(*a, **kw):
        return LLMResult(
            text=json.dumps({"issues": [], "severity_summary": {"critical": 0, "material": 0, "minor": 0}, "overall_verdict": "pass"}),
            cost_rub=0.0,
        )

    monkeypatch.setattr(pm_module, "call_json", _pm_stub)
    monkeypatch.setattr(analyzer_module, "call_json", _an_stub)
    monkeypatch.setattr(synth_module, "call_json", _syn_stub)
    from smart_report import intake as intake_module
    from smart_report import synthesis_critic as critic_module
    monkeypatch.setattr(intake_module, "call_json", _intake_stub)
    monkeypatch.setattr(critic_module, "call_json", _critic_stub)

    client = _authed_client()
    sid = client.post(
        "/api/v4/sessions", json={"question": "what drives success"}
    ).json()["session_id"]

    r = client.post(f"/api/v4/sessions/{sid}/generate-prompt")
    assert r.status_code == 200, r.text

    # Upload two source reports.
    files = [
        ("files", ("perplexity.md", b"# Perplexity sonar report\nPIK, Donstroy.", "text/markdown")),
        ("files", ("claude.md", b"# Claude analysis\nBusiness-class Moscow.", "text/markdown")),
    ]
    r = client.post(f"/api/v4/sessions/{sid}/upload-reports", files=files)
    assert r.status_code == 200, r.text
    uploaded = r.json()
    assert len(uploaded) == 2
    assert uploaded[0]["detected_tool"] in {"perplexity", "other"}
    assert uploaded[1]["detected_tool"] in {"claude", "other"}

    r = client.post(f"/api/v4/sessions/{sid}/analyze")
    assert r.status_code == 202, r.text
    task = r.json()
    assert task["phase"] == "analyze"
    assert task["state"] == "running"
    status = _await_long_task(client, sid, task["task_id"])
    assert status["state"] == "completed", status
    # Result lives on the session, not in the 202 body.
    sess = client.get(f"/api/v4/sessions/{sid}").json()
    analysis = sess["analysis"]
    assert len(analysis["consensus"]) == 1
    assert len(analysis["conflicts"]) == 1
    assert len(analysis["gaps"]) == 1
    assert len(analysis["followup_prompts"]) == 1
    events = client.get(f"/api/v4/sessions/{sid}/events", params={"since": 0, "timeout": 0}).json()["events"]
    depth_events = [ev for ev in events if ev["phase"] == "analytic_depth"]
    assert len(depth_events) >= 2
    assert depth_events[-1]["data"]["research_leads"] >= 1
    assert depth_events[-1]["data"]["disconfirming_probes"] >= 1

    r = client.post(f"/api/v4/sessions/{sid}/synthesize")
    assert r.status_code == 202, r.text
    task = r.json()
    assert task["phase"] == "synthesize"
    status = _await_long_task(client, sid, task["task_id"])
    assert status["state"] == "completed", status
    sess = client.get(f"/api/v4/sessions/{sid}").json()
    final = sess["final_report"]
    assert final["session_id"] == sid
    assert final["executive_summary"]["main_answer"]
    assert final["executive_summary"]["ranking"].startswith("Продукт")

    r = client.get(f"/api/v4/sessions/{sid}/structured-source")
    assert r.status_code == 200, r.text
    structured = r.json()
    assert structured["source"]["metadata"]["title"]
    assert structured["regeneration_plan"]["requested_formats"][:3] == ["docx", "pdf", "pptx"]
    assert structured["publication_quality"] is not None
    assert "metrics" in structured["publication_quality"]
    assert structured["quality_gate"]["passed"] is False
    assert "thin_visual_support" in {
        issue["code"] for issue in structured["quality_gate"]["issues"]
    }
    block_id = structured["source"]["sections"][0]["blocks"][0]["id"]

    r = client.patch(
        f"/api/v4/sessions/{sid}/structured-source",
        json={
            "edits": [
                {
                    "actor_role": "client_reviewer",
                    "target_path": "metadata.title",
                    "value": "Client edited report title",
                    "reason": "Client rename",
                },
                {
                    "actor_role": "editor",
                    "target_path": f"sections.executive_summary.blocks.{block_id}.content",
                    "value": "Edited executive answer.",
                    "reason": "Editor tightened main answer",
                },
            ]
        },
    )
    assert r.status_code == 200, r.text
    edited = r.json()
    assert edited["source"]["metadata"]["title"] == "Client edited report title"
    assert edited["publication_quality"] is not None
    assert len(edited["source"]["versions"]) == 2

    r = client.post(f"/api/v4/sessions/{sid}/apply-remediation", json={})
    assert r.status_code == 200, r.text
    remediated = r.json()
    assert len(remediated["source"]["versions"]) == 3
    assert remediated["publication_quality"] is not None
    assert "remediation_plan" in remediated["publication_quality"]

    r = client.post(
        f"/api/v4/sessions/{sid}/auto-improve",
        json={"max_iterations": 2},
    )
    assert r.status_code == 200, r.text
    auto_improved = r.json()
    assert auto_improved["iterations"]
    assert auto_improved["stopped_reason"] in {
        "ready",
        "no_safe_remediation",
        "no_structural_change",
        "max_iterations_reached",
    }
    assert len(auto_improved["source"]["versions"]) >= 3
    assert auto_improved["regeneration_plan"]["requested_formats"][:3] == ["docx", "pdf", "pptx"]

    r = client.get(f"/api/v4/sessions/{sid}/quality-gate")
    assert r.status_code == 200
    assert r.json()["passed"] is True
    assert remediated["publication_quality"]["ready"] is False

    r = client.post(
        f"/api/v4/sessions/{sid}/regenerate",
        json={"requested_formats": ["pdf"]},
    )
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["publication_quality"] is not None

    r = client.post(
        f"/api/v4/sessions/{sid}/regenerate",
        json={"requested_formats": ["pdf"], "allow_draft": True},
    )
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/zip")
    with zipfile.ZipFile(BytesIO(r.content)) as zf:
        assert "01_premium_report.docx" in set(zf.namelist())
        manifest = json.loads(zf.read("00_manifest.json").decode("utf-8"))
        assert manifest["package_type"] == "smart_report_premium_delivery"

    # Client exports are blocked until readiness gates pass.
    r = client.get(f"/api/v4/sessions/{sid}/export", params={"format": "md"})
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["readiness"]["ready"] is False

    # Draft export is explicit.
    r = client.get(f"/api/v4/sessions/{sid}/export", params={"format": "md", "allow_draft": "true"})
    assert r.status_code == 200, r.text
    assert "Продукт" in r.text or "Product" in r.text
    assert "Метаданные" not in r.text
    assert "language_lint" not in r.text

    # Export json — also confirms content-type routing.
    r = client.get(f"/api/v4/sessions/{sid}/export", params={"format": "json", "allow_draft": "true"})
    assert r.status_code == 200
    # Data-room exports.
    r = client.get(f"/api/v4/sessions/{sid}/export", params={"format": "sources-csv"})
    assert r.status_code == 200
    assert "url" in r.text
    r = client.get(f"/api/v4/sessions/{sid}/export", params={"format": "facts-csv"})
    assert r.status_code == 200
    assert "fact_id" in r.text
    r = client.get(f"/api/v4/sessions/{sid}/export", params={"format": "data-pack"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/zip")
    with zipfile.ZipFile(BytesIO(r.content)) as zf:
        names = set(zf.namelist())
        assert {
            "manifest.json",
            "client_report.json",
            "analytic_depth.json",
            "analytic_closure.json",
            "client_leaks.json",
            "client_readiness.json",
            "premium_readiness.json",
            "sources.csv",
            "facts.csv",
        } <= names
        analytic_depth = json.loads(zf.read("analytic_depth.json").decode("utf-8"))
        assert analytic_depth["root"]["id"] == "root"
        assert analytic_depth["research_leads"]
        analytic_closure = json.loads(zf.read("analytic_closure.json").decode("utf-8"))
        assert analytic_closure["lead_count"] > 0
        assert json.loads(zf.read("client_leaks.json").decode("utf-8")) == []
        readiness = json.loads(zf.read("client_readiness.json").decode("utf-8"))
        assert readiness["ready"] is False
        premium_readiness = json.loads(zf.read("premium_readiness.json").decode("utf-8"))
        assert premium_readiness["score"] < 85
    r = client.get(f"/api/v4/sessions/{sid}/export", params={"format": "audit-json"})
    assert r.status_code == 200
    assert r.json()["analytic_depth"]["research_leads"]
    assert r.json()["analytic_closure"]["lead_count"] > 0
    assert r.json()["premium_readiness"]["ready"] is False
    r = client.get(f"/api/v4/sessions/{sid}/next-research-brief")
    assert r.status_code == 200
    assert "# План добора" in r.text
    assert "## Приоритетные направления добора" in r.text
    assert "**Промпт для добора**" in r.text
    r = client.get(
        f"/api/v4/sessions/{sid}/export",
        params={"format": "next-research-brief", "allow_draft": "true"},
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/markdown")
    assert "# План добора" in r.text
    r = client.get(f"/api/v4/sessions/{sid}/analytic-closure")
    assert r.status_code == 200
    assert r.json()["lead_count"] > 0
    r = client.get(f"/api/v4/sessions/{sid}/premium-readiness")
    assert r.status_code == 200
    assert r.json()["score"] < 85
    r = client.get(
        f"/api/v4/sessions/{sid}/export",
        params={"format": "premium-docx", "allow_draft": "true"},
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    r = client.get(
        f"/api/v4/sessions/{sid}/export",
        params={"format": "premium-pptx", "allow_draft": "true"},
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    )
    r = client.get(
        f"/api/v4/sessions/{sid}/export",
        params={"format": "premium-pdf", "allow_draft": "true"},
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/pdf")
    r = client.get(
        f"/api/v4/sessions/{sid}/export",
        params={"format": "premium-package", "allow_draft": "true"},
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/zip")
    with zipfile.ZipFile(BytesIO(r.content)) as zf:
        names = set(zf.namelist())
        assert {
            "00_manifest.json",
            "01_premium_report.pdf",
            "01_premium_report.docx",
            "02_premium_deck.pptx",
            "03_premium_readiness.json",
            "04_client_readiness.json",
            "05_audit.json",
            "06_analytic_closure.json",
            "07_artifact_qa.json",
            "08_storyboard_quality.json",
            "09_sources.csv",
            "10_facts.csv",
            "11_data_pack.zip",
            "12_evidence_audit.json",
            "13_adjudication_audit.json",
            "14_visual_review.json",
            "15_next_research_brief.md",
            "16_quality_intelligence.json",
        } <= names
        artifact_qa = json.loads(zf.read("07_artifact_qa.json").decode("utf-8"))
        assert artifact_qa["summary"]["artifacts"] == 3
        pdf_qa = next(item for item in artifact_qa["results"] if item["kind"] == "pdf")
        assert pdf_qa["metrics"]["pages"] >= 20
        docx_qa = next(item for item in artifact_qa["results"] if item["kind"] == "docx")
        assert docx_qa["metrics"]["estimated_pages"] >= 1
        if artifact_qa.get("render_index"):
            assert "07_artifact_qa/index.html" in names
            assert any(name.startswith("07_artifact_qa/") and name.endswith(".png") for name in names)
        manifest = json.loads(zf.read("00_manifest.json").decode("utf-8"))
        assert manifest["package_type"] == "smart_report_premium_delivery"
        assert manifest["artifact_qa_status"] in {"passed", "blocked", "failed"}
        assert isinstance(manifest["storyboard_quality_ready"], bool)
        assert manifest["storyboard_quality_score"] >= 0
        assert manifest["docx_pages"] is None or manifest["docx_pages"] >= 1
        assert manifest["docx_pages_source"] in {None, "rendered_pages", "estimated_pages"}
        assert manifest["pdf_pages"] is None or manifest["pdf_pages"] >= 20
        assert manifest["deck_slides"] is None or manifest["deck_slides"] >= 10
        assert isinstance(manifest["open_analytic_leads"], int)
        assert isinstance(manifest["unsupported_conclusions"], int)
        audit = json.loads(zf.read("05_audit.json").decode("utf-8"))
        storyboard_quality = json.loads(zf.read("08_storyboard_quality.json").decode("utf-8"))
        assert isinstance(storyboard_quality["ready"], bool)
        assert storyboard_quality["metrics"]["page_count"] >= 8
        visual_review = json.loads(zf.read("14_visual_review.json").decode("utf-8"))
        assert audit["visual_review"]["status"] == visual_review["status"]
        assert visual_review["status"] in {"pending", "blocked"}
        brief = zf.read("15_next_research_brief.md").decode("utf-8")
        assert "# План добора" in brief
        assert "## Приоритетные направления добора" in brief
        assert "Рекомендуемый сервис:" in brief
        assert "**Промпт для добора**" in brief
        assert "**Зачем это важно**" in brief
        assert "- Кандидаты источников:" in brief
        assert "## Quality intelligence: что именно закрыть" in brief
        assert "Evidence graph:" in brief
        assert "Research policy:" in brief
        quality = json.loads(zf.read("16_quality_intelligence.json").decode("utf-8"))
        assert {
            "evidence_graph",
            "research_policy",
            "page_plan",
            "benchmark_eval",
        } <= set(quality)
        assert "summary" in quality["evidence_graph"]
        assert "issues" in quality["benchmark_eval"]
    r = client.get(
        f"/api/v4/sessions/{sid}/export",
        params={"format": "premium-client-package"},
    )
    assert r.status_code == 409
    blockers = set(r.json()["detail"]["gate"]["blockers"])
    assert {
        "client_readiness_not_ready",
        "premium_readiness_not_ready",
        "analytic_closure_open_leads",
        "evidence_audit_unsupported_conclusions",
        "adjudication_audit_critical_unresolved",
        "artifact_qa_not_passed",
        "storyboard_quality_not_ready",
        "visual_review_not_approved",
    } <= blockers
    # Export gamma-pdf stub.
    r = client.get(f"/api/v4/sessions/{sid}/export", params={"format": "gamma-pdf", "allow_draft": "true"})
    assert r.status_code == 200
    # Unknown format.
    r = client.get(f"/api/v4/sessions/{sid}/export", params={"format": "foo"})
    assert r.status_code == 400

    # Final session view.
    r = client.get(f"/api/v4/sessions/{sid}")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "synthesized"
    assert body["final_report"] is not None
    # Each of the 3 LLM steps returned cost_rub=0.12 → total should be 0.36.
    assert body["total_cost_rub"] == pytest.approx(0.36, abs=1e-3)


def test_auto_dr_appends_to_source_reports(monkeypatch):
    """Mock auto_dr.run_auto_dr → returns a fake markdown; verify endpoint
    appends to source_reports + bumps cost + flips status."""
    from smart_report.models import UploadedMarkdown
    from smart_report.sources import auto_dr as auto_dr_mod

    async def _fake_run(service, question, *, domain_hint=None, max_results=10):
        return auto_dr_mod.AutoDRResult(
            upload=UploadedMarkdown(
                filename=f"auto_dr_{service}.md",
                content=f"# {service} stub\n\nfake markdown",
                detected_tool="other",
                word_count=4,
            ),
            service=service,
            cost_usd=0.005,
            cost_rub=0.377,
            source_count=3,
            notes="stub",
        )

    monkeypatch.setattr(auto_dr_mod, "run_auto_dr", _fake_run)

    client = _authed_client()
    sid = client.post(
        "/api/v4/sessions", json={"question": "test research question"}
    ).json()["session_id"]

    r = client.post(
        f"/api/v4/sessions/{sid}/auto-dr",
        json={"service": "tavily", "prompt": "find me X"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["service"] == "tavily"
    assert body["source_count"] == 3
    assert body["cost_usd"] == pytest.approx(0.005, abs=1e-6)

    # Session state mutated: source_reports has the new upload, status flipped.
    sess = client.get(f"/api/v4/sessions/{sid}").json()
    assert len(sess["source_reports"]) == 1
    assert sess["source_reports"][0]["filename"] == "auto_dr_tavily.md"
    assert sess["status"] == "reports_uploaded"
    assert sess["total_cost_rub"] == pytest.approx(0.377, abs=1e-3)


def test_auto_dr_rejects_unknown_service():
    client = _authed_client()
    sid = client.post(
        "/api/v4/sessions", json={"question": "test research question"}
    ).json()["session_id"]
    r = client.post(
        f"/api/v4/sessions/{sid}/auto-dr",
        json={"service": "google", "prompt": "x"},
    )
    # pydantic Literal validation rejects unknown service before reaching handler
    assert r.status_code == 422, r.text


def test_auto_dr_surfaces_backend_error_as_502(monkeypatch):
    from smart_report.sources import auto_dr as auto_dr_mod

    async def _fail(*args, **kwargs):
        raise auto_dr_mod.AutoDRError("valyu returned empty/error: no results")

    monkeypatch.setattr(auto_dr_mod, "run_auto_dr", _fail)

    client = _authed_client()
    sid = client.post(
        "/api/v4/sessions", json={"question": "test research question"}
    ).json()["session_id"]
    r = client.post(
        f"/api/v4/sessions/{sid}/auto-dr",
        json={"service": "valyu", "prompt": "obscure thing"},
    )
    assert r.status_code == 502, r.text
    assert "valyu" in r.json()["detail"].lower()


def test_auto_dr_falls_back_to_session_question_when_prompt_empty(monkeypatch):
    """If client omits `prompt`, the endpoint reuses the session's question
    (or the generated research_prompt) — UX optimization for the picker
    that fires before the user has manually edited the prompt."""
    from smart_report.models import UploadedMarkdown
    from smart_report.sources import auto_dr as auto_dr_mod

    captured = {}

    async def _capture(service, question, *, domain_hint=None, max_results=10):
        captured["question"] = question
        return auto_dr_mod.AutoDRResult(
            upload=UploadedMarkdown(
                filename="x.md", content="x", detected_tool="other", word_count=1,
            ),
            service=service,
            cost_usd=0.0, cost_rub=0.0, source_count=0, notes="",
        )

    monkeypatch.setattr(auto_dr_mod, "run_auto_dr", _capture)

    client = _authed_client()
    sid = client.post(
        "/api/v4/sessions", json={"question": "what is the meaning of life"}
    ).json()["session_id"]
    r = client.post(
        f"/api/v4/sessions/{sid}/auto-dr",
        json={"service": "tavily"},  # no prompt
    )
    assert r.status_code == 200, r.text
    assert captured["question"] == "what is the meaning of life"


def test_cancel_marks_session_and_blocks_further_spend():
    client = _authed_client()
    sid = client.post(
        "/api/v4/sessions", json={"question": "test research question"}
    ).json()["session_id"]

    r = client.post(f"/api/v4/sessions/{sid}/cancel")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "cancelled"

    sess = client.get(f"/api/v4/sessions/{sid}").json()
    assert sess["status"] == "cancelled"

    # Any LLM-spending endpoint now 409s.
    r2 = client.post(f"/api/v4/sessions/{sid}/generate-prompt")
    assert r2.status_code == 409, r2.text
    assert "cancel" in r2.json()["detail"].lower()


def test_cancel_is_idempotent():
    client = _authed_client()
    sid = client.post(
        "/api/v4/sessions", json={"question": "test research question"}
    ).json()["session_id"]
    r1 = client.post(f"/api/v4/sessions/{sid}/cancel")
    r2 = client.post(f"/api/v4/sessions/{sid}/cancel")
    assert r1.status_code == 200 and r2.status_code == 200
    assert r2.json()["status"] == "cancelled"


def test_delete_removes_session_and_returns_204():
    client = _authed_client()
    sid = client.post(
        "/api/v4/sessions", json={"question": "test research question"}
    ).json()["session_id"]

    r = client.delete(f"/api/v4/sessions/{sid}")
    assert r.status_code == 204, r.text

    # GET is now 404 (session gone).
    r2 = client.get(f"/api/v4/sessions/{sid}")
    assert r2.status_code == 404


def test_delete_404s_when_session_missing():
    client = _authed_client()
    r = client.delete("/api/v4/sessions/doesnotexist00")
    assert r.status_code == 404


def test_delete_403s_when_not_owner():
    """Owner of session A cannot DELETE session of user B."""
    # User B creates a session
    cb = TestClient(app)
    rb = cb.post("/api/auth/signup", json={"email": "userb@example.com", "password": "test1234"})
    assert rb.status_code == 201, rb.text
    sid = cb.post("/api/v4/sessions", json={"question": "user b's question"}).json()["session_id"]
    # User A tries to delete it
    ca = _authed_client()
    r = ca.delete(f"/api/v4/sessions/{sid}")
    assert r.status_code == 403, r.text


def test_auto_dr_async_path_returns_task_id_and_charges_upfront(monkeypatch):
    """When mode is set, auto-dr submits a Valyu Research job and returns task_id."""
    from smart_report.sources import auto_dr as auto_dr_mod

    submitted: dict = {}

    async def _fake_submit(service, question, *, mode="standard", session_id=None, store=None):
        submitted["service"] = service
        submitted["question"] = question
        submitted["mode"] = mode
        return auto_dr_mod.AsyncResearchSubmission(
            task_id="task-xyz-123",
            service="valyu",
            mode=mode,
            cost_usd=0.50,
            eta_min_low=10,
            eta_min_high=20,
        )

    monkeypatch.setattr(auto_dr_mod, "submit_async_research", _fake_submit)

    client = _authed_client()
    sid = client.post(
        "/api/v4/sessions", json={"question": "test research async flow"}
    ).json()["session_id"]

    r = client.post(
        f"/api/v4/sessions/{sid}/auto-dr",
        json={"service": "valyu", "mode": "standard", "prompt": "deep dive on X"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["task_id"] == "task-xyz-123"
    assert body["mode"] == "standard"
    assert body["cost_usd"] == pytest.approx(0.50)
    assert body["eta_min_low"] == 10
    assert "10–20" in body["message"] or "10-20" in body["message"]

    # Cost charged upfront, job tracked in pending_dr_jobs
    sess = client.get(f"/api/v4/sessions/{sid}").json()
    assert len(sess["pending_dr_jobs"]) == 1
    assert sess["pending_dr_jobs"][0]["task_id"] == "task-xyz-123"
    assert sess["total_cost_rub"] > 30  # 0.50 * 75.4 = ~37


def test_auto_dr_status_running_returns_state(monkeypatch):
    from smart_report.sources import auto_dr as auto_dr_mod

    async def _fake_submit(service, question, *, mode="standard", session_id=None, store=None):
        return auto_dr_mod.AsyncResearchSubmission(
            task_id="t1", service="valyu", mode=mode,
            cost_usd=0.50, eta_min_low=10, eta_min_high=20,
        )

    async def _fake_poll(task_id, *, service="valyu", mode="standard"):
        return auto_dr_mod.AsyncResearchPoll(state="running", progress_pct=42, message="searching…")

    monkeypatch.setattr(auto_dr_mod, "submit_async_research", _fake_submit)
    monkeypatch.setattr(auto_dr_mod, "try_collect_async_research", _fake_poll)

    client = _authed_client()
    sid = client.post(
        "/api/v4/sessions", json={"question": "test research async flow"}
    ).json()["session_id"]
    client.post(
        f"/api/v4/sessions/{sid}/auto-dr",
        json={"service": "valyu", "mode": "standard", "prompt": "x"},
    )
    r = client.get(f"/api/v4/sessions/{sid}/auto-dr-status?task_id=t1")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["state"] == "running"
    assert body["progress_pct"] == 42


def test_auto_dr_status_completed_appends_to_source_reports(monkeypatch):
    from smart_report.models import UploadedMarkdown
    from smart_report.sources import auto_dr as auto_dr_mod

    async def _fake_submit(service, question, *, mode="standard", session_id=None, store=None):
        return auto_dr_mod.AsyncResearchSubmission(
            task_id="t2", service="valyu", mode=mode,
            cost_usd=0.50, eta_min_low=10, eta_min_high=20,
        )

    async def _fake_poll(task_id, *, service="valyu", mode="standard"):
        return auto_dr_mod.AsyncResearchPoll(
            state="completed",
            result=auto_dr_mod.AutoDRResult(
                upload=UploadedMarkdown(
                    filename="valyu_research_standard_t2.md",
                    content="# Final report\n\nSome findings.",
                    detected_tool="other",
                    word_count=4,
                ),
                service="valyu",
                cost_usd=0.50, cost_rub=37.7, source_count=8, notes="test",
            ),
        )

    monkeypatch.setattr(auto_dr_mod, "submit_async_research", _fake_submit)
    monkeypatch.setattr(auto_dr_mod, "try_collect_async_research", _fake_poll)

    client = _authed_client()
    sid = client.post(
        "/api/v4/sessions", json={"question": "test research async flow"}
    ).json()["session_id"]
    client.post(
        f"/api/v4/sessions/{sid}/auto-dr",
        json={"service": "valyu", "mode": "standard", "prompt": "x"},
    )
    r = client.get(f"/api/v4/sessions/{sid}/auto-dr-status?task_id=t2")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["state"] == "completed"
    assert body["filename"] == "valyu_research_standard_t2.md"
    assert body["source_count"] == 8

    # Source appended, job removed from pending
    sess = client.get(f"/api/v4/sessions/{sid}").json()
    assert len(sess["source_reports"]) == 1
    assert sess["source_reports"][0]["filename"] == "valyu_research_standard_t2.md"
    assert sess["pending_dr_jobs"] == []


def test_auto_dr_cancel_openai_soft_cancel_when_no_live_task(monkeypatch):
    """After container restart there's no live asyncio.Task, but the
    endpoint must still clean the pending_dr_jobs entry (soft cancel).
    Old behaviour returned 410; new behaviour returns 200 with kind=soft."""
    from smart_report.sources import auto_dr as auto_dr_mod

    async def _fake_submit(service, question, *, mode="standard", session_id=None, store=None):
        return auto_dr_mod.AsyncResearchSubmission(
            task_id="oai-cancel-test", service="openai", mode="mini",
            cost_usd=0.50, eta_min_low=5, eta_min_high=10,
        )

    monkeypatch.setattr(auto_dr_mod, "submit_async_research", _fake_submit)

    client = _authed_client()
    sid = client.post(
        "/api/v4/sessions", json={"question": "openai cancel test"}
    ).json()["session_id"]
    client.post(
        f"/api/v4/sessions/{sid}/auto-dr",
        json={"service": "openai", "mode": "mini", "prompt": "x"},
    )
    r = client.post(f"/api/v4/sessions/{sid}/auto-dr-cancel?task_id=oai-cancel-test")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["state"] == "cancelled"
    assert body["kind"] == "soft"  # no live task → soft
    # pending_dr_jobs entry removed
    sess = client.get(f"/api/v4/sessions/{sid}").json()
    assert all(j.get("task_id") != "oai-cancel-test" for j in (sess.get("pending_dr_jobs") or []))


def test_auto_dr_cancel_tavily_is_soft_cancel(monkeypatch):
    """Tavily SDK has no cancel method — endpoint returns 200 with kind=soft."""
    from smart_report.sources import auto_dr as auto_dr_mod

    async def _fake_submit(service, question, *, mode="standard", session_id=None, store=None):
        return auto_dr_mod.AsyncResearchSubmission(
            task_id="tav-cancel-test", service="tavily", mode="mini",
            cost_usd=0.05, eta_min_low=2, eta_min_high=5,
        )

    monkeypatch.setattr(auto_dr_mod, "submit_async_research", _fake_submit)

    client = _authed_client()
    sid = client.post(
        "/api/v4/sessions", json={"question": "tavily soft cancel"}
    ).json()["session_id"]
    client.post(
        f"/api/v4/sessions/{sid}/auto-dr",
        json={"service": "tavily", "mode": "mini", "prompt": "x"},
    )
    r = client.post(f"/api/v4/sessions/{sid}/auto-dr-cancel?task_id=tav-cancel-test")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["state"] == "cancelled"
    assert body["kind"] == "soft"
    sess = client.get(f"/api/v4/sessions/{sid}").json()
    assert all(j.get("task_id") != "tav-cancel-test" for j in (sess.get("pending_dr_jobs") or []))


def test_auto_dr_cancel_valyu_attempts_hard_cancel(monkeypatch):
    """Valyu wrapper attempts SDK cancel — falls back to soft if it raises.
    Without VALYU_API_KEY in test env, the call is skipped and we get soft."""
    from smart_report.sources import auto_dr as auto_dr_mod

    async def _fake_submit(service, question, *, mode="standard", session_id=None, store=None):
        return auto_dr_mod.AsyncResearchSubmission(
            task_id="valyu-cancel-test", service="valyu", mode="standard",
            cost_usd=0.50, eta_min_low=10, eta_min_high=20,
        )

    monkeypatch.setattr(auto_dr_mod, "submit_async_research", _fake_submit)
    monkeypatch.delenv("VALYU_API_KEY", raising=False)  # force soft-cancel path

    client = _authed_client()
    sid = client.post(
        "/api/v4/sessions", json={"question": "valyu cancel test"}
    ).json()["session_id"]
    client.post(
        f"/api/v4/sessions/{sid}/auto-dr",
        json={"service": "valyu", "mode": "standard", "prompt": "x"},
    )
    r = client.post(f"/api/v4/sessions/{sid}/auto-dr-cancel?task_id=valyu-cancel-test")
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "cancelled"
    # Without API key, soft-cancel; with key it'd be hard.
    assert r.json()["kind"] == "soft"


def test_get_analytic_depth_requires_analysis():
    client = _authed_client()
    sid = client.post(
        "/api/v4/sessions",
        json={"question": "forecast Moscow premium real estate prices"},
    ).json()["session_id"]

    r = client.get(f"/api/v4/sessions/{sid}/analytic-depth")

    assert r.status_code == 409
    assert "call /analyze first" in r.text


def test_next_research_brief_requires_analysis_but_not_final_report():
    from smart_report.models import AnalysisOutput, Gap

    client = _authed_client()
    sid = client.post(
        "/api/v4/sessions",
        json={"question": "forecast Moscow premium real estate prices"},
    ).json()["session_id"]

    r = client.get(f"/api/v4/sessions/{sid}/next-research-brief")
    assert r.status_code == 409
    assert "call /analyze first" in r.text

    session = v4._store.get(sid)
    session.analysis = AnalysisOutput(
        gaps=[
            Gap(
                topic="Pipeline starts",
                why_critical="Supply changes price pressure.",
                what_to_find="Named launches with dates and source URLs.",
                candidate_sources=["developer sites"],
            )
        ]
    )
    session.final_report = None
    v4._store.update(session)

    r = client.get(f"/api/v4/sessions/{sid}/next-research-brief")
    assert r.status_code == 200, r.text
    assert "# План добора" in r.text
    assert "Pipeline starts" in r.text
    assert "**Промпт для добора**" in r.text


def test_get_analytic_depth_plan_returns_research_map():
    from smart_report.models import AnalysisOutput, Conflict, Gap, UnverifiedNumber

    client = _authed_client()
    sid = client.post(
        "/api/v4/sessions",
        json={"question": "forecast Moscow primary real estate prices in 2026"},
    ).json()["session_id"]
    session = v4._store.get(sid)
    session.analysis = AnalysisOutput(
        conflicts=[
            Conflict(
                topic="Q1 2026 price baseline",
                source_a="Metrium PDF",
                claim_a="business class is 561450 RUB per sqm",
                source_b="aggregated report",
                claim_b="business class is 887780 RUB per sqm",
                resolution_hint="Separate business and premium segments.",
                importance="critical",
            )
        ],
        gaps=[
            Gap(
                topic="2026-2027 project pipeline",
                why_critical="Supply launches can change price pressure.",
                what_to_find="Named business and premium starts with timing and GBA.",
                candidate_sources=["developer sites", "stroi.mos.ru", "erzrf.ru"],
            )
        ],
        unverified_numbers=[
            UnverifiedNumber(
                value="887780",
                metric="price per sqm",
                subject="business class",
                source_tool="uploaded report",
                why_unverified="Likely premium value mislabeled as business.",
            )
        ],
    )
    v4._store.update(session)

    r = client.get(f"/api/v4/sessions/{sid}/analytic-depth")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["domain_hint"] == "russian_market"
    assert body["root"]["id"] == "root"
    assert {child["id"] for child in body["root"]["children"]} == {
        "evidence_base",
        "hypotheses",
        "benchmarks",
        "decision",
    }
    assert any(lead["kind"] == "resolve_conflict" for lead in body["research_leads"])
    assert any(lead["kind"] == "verify_number" for lead in body["research_leads"])
    assert any(probe["disconfirming"] for probe in body["evidence_probes"])


def test_auto_depth_leads_submits_research_jobs(monkeypatch):
    from smart_report.models import AnalysisOutput, Conflict, Gap, UnverifiedNumber
    from smart_report.sources import auto_dr as auto_dr_mod

    async def _fake_submit(service, question, *, mode="standard", session_id=None, store=None):
        suffix = abs(hash(question)) % 10000
        return auto_dr_mod.AsyncResearchSubmission(
            task_id=f"{service}-{suffix}",
            service=service,
            mode=mode,
            cost_usd=0.25,
            eta_min_low=3,
            eta_min_high=7,
        )

    monkeypatch.setattr(auto_dr_mod, "submit_async_research", _fake_submit)

    client = _authed_client()
    sid = client.post(
        "/api/v4/sessions",
        json={"question": "forecast Moscow primary real estate prices in 2026"},
    ).json()["session_id"]
    session = v4._store.get(sid)
    session.analysis = AnalysisOutput(
        conflicts=[
            Conflict(
                topic="Q1 2026 price baseline",
                source_a="Metrium PDF",
                claim_a="business class is 561450 RUB per sqm",
                source_b="aggregated report",
                claim_b="business class is 887780 RUB per sqm",
                resolution_hint="Separate business and premium segments.",
                importance="critical",
            )
        ],
        gaps=[
            Gap(
                topic="Pipeline starts",
                why_critical="Supply changes price pressure.",
                what_to_find="Named launches with timing.",
                candidate_sources=["developer sites"],
            )
        ],
        unverified_numbers=[
            UnverifiedNumber(
                value="887780",
                metric="price per sqm",
                subject="business class",
                source_tool="uploaded report",
            )
        ],
    )
    v4._store.update(session)

    r = client.post(
        f"/api/v4/sessions/{sid}/auto-depth-leads",
        json={"max_leads": 2, "include_priority": "must", "service_override": "openai", "mode_override": "mini"},
    )

    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body) == 2
    assert all(item["service"] == "openai" for item in body)
    assert all(item["rationale"] for item in body)
    assert all(isinstance(item["candidate_sources"], list) for item in body)
    assert all(isinstance(item["linked_to"], list) for item in body)
    assert all(item["prompt_preview"] for item in body)
    stored = v4._store.get(sid)
    jobs = stored.pending_dr_jobs
    assert len(jobs) == 2
    assert all(job["analytic_depth"]["lead_id"] for job in jobs)
    assert all(job["analytic_depth"]["rationale"] for job in jobs)
    assert all(isinstance(job["analytic_depth"]["candidate_sources"], list) for job in jobs)
    assert all(isinstance(job["analytic_depth"]["linked_to"], list) for job in jobs)
    assert all(job["is_followup"] is True for job in jobs)
    assert stored.total_cost_rub > 0
    events = client.get(f"/api/v4/sessions/{sid}/events", params={"since": 0, "timeout": 0}).json()["events"]
    assert any(
        ev["phase"] == "analytic_depth"
        and ev["data"].get("stage") == "auto_depth_leads_submitted"
        for ev in events
    )


def test_async_mode_for_lead_rejects_invalid_provider_override():
    class Lead:
        recommended_mode = "standard"

    assert v4._async_mode_for_lead("perplexity", Lead(), "standard") == "deep"
    assert v4._async_mode_for_lead("perplexity", Lead(), None) == "deep"
    assert v4._async_mode_for_lead("openai", Lead(), "DEEP") == "deep"


def test_premium_refine_waits_for_running_followup_jobs():
    from smart_report.models import AnalysisOutput, Gap

    client = _authed_client()
    sid = client.post(
        "/api/v4/sessions",
        json={"question": "forecast Moscow primary real estate prices in 2026"},
    ).json()["session_id"]
    session = v4._store.get(sid)
    session.analysis = AnalysisOutput(
        gaps=[
            Gap(
                topic="Pipeline starts",
                why_critical="Supply changes price pressure.",
                what_to_find="Named launches with timing.",
                candidate_sources=["developer sites"],
            )
        ]
    )
    session.pending_dr_jobs = [
        {
            "task_id": "depth-running",
            "service": "openai",
            "mode": "mini",
            "state": "running",
            "is_followup": True,
            "analytic_depth": {"lead_id": "gap_1"},
        }
    ]
    v4._store.update(session)

    r = client.post(f"/api/v4/sessions/{sid}/premium-refine", json={})

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["action"] == "wait_for_followups"
    assert body["pending_task_ids"] == ["depth-running"]


def test_premium_refinement_status_recommends_next_step():
    from smart_report.models import AnalysisOutput, Gap

    client = _authed_client()
    sid = client.post(
        "/api/v4/sessions",
        json={"question": "forecast Moscow primary real estate prices in 2026"},
    ).json()["session_id"]

    r = client.get(f"/api/v4/sessions/{sid}/premium-refinement-status")
    assert r.status_code == 200, r.text
    assert r.json()["recommended_action"] == "run_analysis"

    session = v4._store.get(sid)
    session.analysis = AnalysisOutput(
        gaps=[
            Gap(
                topic="Pipeline starts",
                why_critical="Supply changes price pressure.",
                what_to_find="Named launches with timing.",
                candidate_sources=["developer sites"],
            )
        ]
    )
    v4._store.update(session)

    r = client.get(f"/api/v4/sessions/{sid}/premium-refinement-status")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["recommended_action"] == "submit_followups"
    assert body["analytic_closure"]["lead_count"] > 0
    assert body["final_report_needs_followup_resynthesis"] is True
    assert body["next_research_leads"]
    first_lead = body["next_research_leads"][0]
    assert first_lead["status"] == "not_started"
    assert first_lead["prompt_preview"]
    assert first_lead["service"] in {"valyu", "perplexity", "openai", "exa", "tavily"}


def test_premium_refine_submits_open_analytic_depth_leads(monkeypatch):
    from smart_report.models import AnalysisOutput, Gap
    from smart_report.sources import auto_dr as auto_dr_mod

    async def _fake_submit(service, question, *, mode="standard", session_id=None, store=None):
        return auto_dr_mod.AsyncResearchSubmission(
            task_id="depth-submit",
            service=service,
            mode=mode,
            cost_usd=0.25,
            eta_min_low=3,
            eta_min_high=7,
        )

    monkeypatch.setattr(auto_dr_mod, "submit_async_research", _fake_submit)

    client = _authed_client()
    sid = client.post(
        "/api/v4/sessions",
        json={"question": "forecast Moscow primary real estate prices in 2026"},
    ).json()["session_id"]
    session = v4._store.get(sid)
    session.analysis = AnalysisOutput(
        gaps=[
            Gap(
                topic="Pipeline starts",
                why_critical="Supply changes price pressure.",
                what_to_find="Named launches with timing.",
                candidate_sources=["developer sites"],
            )
        ]
    )
    v4._store.update(session)

    r = client.post(
        f"/api/v4/sessions/{sid}/premium-refine",
        json={"max_leads": 1, "service_override": "openai", "mode_override": "mini"},
    )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["action"] == "submitted_followups"
    assert len(body["submitted_leads"]) == 1
    stored = v4._store.get(sid)
    assert stored.pending_dr_jobs[0]["is_followup"] is True
    assert stored.pending_dr_jobs[0]["analytic_depth"]["lead_id"]


def test_premium_refine_starts_synthesis_after_followup_without_open_leads(monkeypatch):
    from smart_report.analytic_depth import AnalyticDepthPlan, InquiryNode
    from smart_report.models import AnalysisOutput, UploadedMarkdown

    def _fake_start_long_task(session, *, phase, model_preference, coro_factory):  # noqa: ARG001
        return v4.LongTaskOut(
            task_id="synth-refine",
            phase="synthesize",
            state="running",
            started_at="2026-04-30T00:00:00+00:00",
        )

    monkeypatch.setattr(v4, "_start_long_task", _fake_start_long_task)
    monkeypatch.setattr(
        v4,
        "build_analytic_depth_plan",
        lambda *args, **kwargs: AnalyticDepthPlan(
            question="q",
            domain_hint="market_general",
            root=InquiryNode(id="root", question="q", rationale="r"),
            hypotheses=[],
            evidence_probes=[],
            research_leads=[],
            benchmark_questions=[],
            monitoring_indicators=[],
        ),
    )

    client = _authed_client()
    sid = client.post(
        "/api/v4/sessions",
        json={"question": "forecast Moscow primary real estate prices in 2026"},
    ).json()["session_id"]
    session = v4._store.get(sid)
    session.source_reports = [
        UploadedMarkdown(
            filename="source.md",
            content="Source material with https://example.com/source and 7.2% growth.",
            detected_tool="other",
            word_count=8,
        )
    ]
    session.followup_reports = [
        UploadedMarkdown(
            filename="followup.md",
            content="Follow-up material with https://example.com/followup and 7.2% growth.",
            detected_tool="other",
            word_count=8,
        )
    ]
    session.analysis = AnalysisOutput()
    v4._store.update(session)

    r = client.post(f"/api/v4/sessions/{sid}/premium-refine", json={})

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["action"] == "synthesize_started"
    assert body["synthesize_task"]["task_id"] == "synth-refine"


def test_auto_dr_status_preserves_analytic_depth_metadata_on_followup(monkeypatch):
    from smart_report.models import AnalysisOutput, Gap, UploadedMarkdown
    from smart_report.sources import auto_dr as auto_dr_mod

    async def _fake_poll(task_id, *, service="valyu", mode="standard"):
        return auto_dr_mod.AsyncResearchPoll(
            state="completed",
            result=auto_dr_mod.AutoDRResult(
                upload=UploadedMarkdown(
                    filename="valyu_research_standard_depth.md",
                    content=(
                        "# Follow-up\n\n"
                        "According to https://example.com/source, the metric is 7.2%."
                    ),
                    detected_tool="other",
                    word_count=8,
                ),
                service="valyu",
                cost_usd=0.1,
                cost_rub=7.54,
                source_count=1,
            ),
        )

    monkeypatch.setattr(auto_dr_mod, "try_collect_async_research", _fake_poll)

    client = _authed_client()
    sid = client.post(
        "/api/v4/sessions",
        json={"question": "forecast Moscow primary real estate prices in 2026"},
    ).json()["session_id"]
    session = v4._store.get(sid)
    session.analysis = AnalysisOutput(
        gaps=[
            Gap(
                topic="Real transaction prices",
                why_critical="Asking prices can overstate the entry price.",
                what_to_find="Transaction-level evidence by segment.",
                candidate_sources=["official registry"],
            )
        ]
    )
    session.pending_dr_jobs = [
        {
            "task_id": "depth-task",
            "service": "valyu",
            "mode": "standard",
            "state": "running",
            "is_followup": True,
            "analytic_depth": {
                "lead_id": "gap_1",
                "kind": "close_gap",
                "priority": "must",
                "rationale": "Close transaction-price evidence gap.",
                "candidate_sources": ["official registry"],
                "linked_to": ["gap:Real transaction prices"],
            },
        }
    ]
    v4._store.update(session)

    r = client.get(f"/api/v4/sessions/{sid}/auto-dr-status?task_id=depth-task")

    assert r.status_code == 200, r.text
    stored = client.get(f"/api/v4/sessions/{sid}").json()
    assert len(stored["followup_reports"]) == 1
    content = stored["followup_reports"][0]["content"]
    assert "Smart Report analytic-depth lead: gap_1" in content
    closure = client.get(f"/api/v4/sessions/{sid}/analytic-closure")
    assert closure.status_code == 200
    assert closure.json()["partial"] + closure.json()["closed"] >= 1


def test_auto_dr_status_finds_completed_llm_followup_after_pending_removed():
    from smart_report.models import UploadedMarkdown

    client = _authed_client()
    sid = client.post(
        "/api/v4/sessions",
        json={"question": "forecast Moscow primary real estate prices in 2026"},
    ).json()["session_id"]
    session = v4._store.get(sid)
    session.pending_dr_jobs = []
    session.followup_reports = [
        UploadedMarkdown(
            filename="auto_followup_openai_abc12345.md",
            content=(
                "<!-- Smart Report analytic-depth metadata\n"
                "Smart Report analytic-depth lead: gap_1\n"
                "-->\n\n"
                "Follow-up evidence from https://example.com/source shows 7.2%."
            ),
            detected_tool="other",
            word_count=16,
        )
    ]
    v4._store.update(session)

    r = client.get(f"/api/v4/sessions/{sid}/auto-dr-status?task_id=abc12345-deadbeef")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["state"] == "completed"
    assert body["filename"] == "auto_followup_openai_abc12345.md"
    assert body["word_count"] == 16


def test_auto_dr_accept_partial_promotes_to_source_reports(monkeypatch):
    """When LLM DR was interrupted with partial content, accepting it
    moves partial_content to source_reports and removes the job entry."""
    from smart_report.sources import auto_dr as auto_dr_mod

    async def _fake_submit(service, question, *, mode="standard", session_id=None, store=None):
        return auto_dr_mod.AsyncResearchSubmission(
            task_id="oai-partial", service="openai", mode="mini",
            cost_usd=0.50, eta_min_low=5, eta_min_high=10,
        )

    monkeypatch.setattr(auto_dr_mod, "submit_async_research", _fake_submit)

    client = _authed_client()
    sid = client.post(
        "/api/v4/sessions", json={"question": "partial accept test"}
    ).json()["session_id"]
    client.post(
        f"/api/v4/sessions/{sid}/auto-dr",
        json={"service": "openai", "mode": "mini", "prompt": "x"},
    )
    # Simulate the streaming runner having flushed some partial content,
    # then the container being killed → state=interrupted_with_partial
    from smart_report.api import v4_endpoints as v4
    s = v4._store.get(sid)
    for j in s.pending_dr_jobs:
        if j["task_id"] == "oai-partial":
            j["partial_content"] = "# Partial DR result\n\nSome findings so far"
            j["partial_chars"] = 41
            j["state"] = "interrupted_with_partial"
    v4._store.update(s)

    r = client.post(f"/api/v4/sessions/{sid}/auto-dr-accept-partial?task_id=oai-partial")
    assert r.status_code == 200, r.text

    sess = client.get(f"/api/v4/sessions/{sid}").json()
    # source_reports has the partial as an upload, with _partial suffix
    assert any(
        u["filename"] == "auto_dr_openai_oai-part_partial.md"
        for u in sess["source_reports"]
    )
    # Job removed from pending_dr_jobs
    assert all(j["task_id"] != "oai-partial" for j in (sess.get("pending_dr_jobs") or []))


def test_auto_dr_accept_partial_routes_analytic_depth_to_followups(monkeypatch):
    from smart_report.sources import auto_dr as auto_dr_mod

    async def _fake_submit(service, question, *, mode="standard", session_id=None, store=None):
        return auto_dr_mod.AsyncResearchSubmission(
            task_id="oai-depth-partial",
            service="openai",
            mode="mini",
            cost_usd=0.50,
            eta_min_low=5,
            eta_min_high=10,
        )

    monkeypatch.setattr(auto_dr_mod, "submit_async_research", _fake_submit)

    client = _authed_client()
    sid = client.post(
        "/api/v4/sessions", json={"question": "partial analytic-depth accept test"}
    ).json()["session_id"]
    client.post(
        f"/api/v4/sessions/{sid}/auto-dr",
        json={"service": "openai", "mode": "mini", "prompt": "x"},
    )
    s = v4._store.get(sid)
    for job in s.pending_dr_jobs:
        if job["task_id"] == "oai-depth-partial":
            job["partial_content"] = "# Partial follow-up\n\nhttps://example.com says 7.2%."
            job["partial_chars"] = len(job["partial_content"])
            job["state"] = "interrupted_with_partial"
            job["is_followup"] = True
            job["analytic_depth"] = {
                "lead_id": "gap_1",
                "kind": "close_gap",
                "priority": "must",
                "rationale": "Close the gap.",
                "candidate_sources": ["official registry"],
                "linked_to": ["gap:prices"],
            }
    v4._store.update(s)

    r = client.post(f"/api/v4/sessions/{sid}/auto-dr-accept-partial?task_id=oai-depth-partial")

    assert r.status_code == 200, r.text
    sess = client.get(f"/api/v4/sessions/{sid}").json()
    assert sess["source_reports"] == []
    assert len(sess["followup_reports"]) == 1
    assert sess["followup_reports"][0]["filename"] == "auto_followup_openai_oai-dept_partial.md"
    assert "Smart Report analytic-depth lead: gap_1" in sess["followup_reports"][0]["content"]
    assert all(j["task_id"] != "oai-depth-partial" for j in (sess.get("pending_dr_jobs") or []))


def test_auto_dr_accept_partial_404_when_no_partial():
    client = _authed_client()
    sid = client.post(
        "/api/v4/sessions", json={"question": "test"}
    ).json()["session_id"]
    r = client.post(f"/api/v4/sessions/{sid}/auto-dr-accept-partial?task_id=ghost")
    assert r.status_code == 404


def test_auto_dr_cancel_404_for_unknown_task():
    client = _authed_client()
    sid = client.post(
        "/api/v4/sessions", json={"question": "cancel 404 test"}
    ).json()["session_id"]
    r = client.post(f"/api/v4/sessions/{sid}/auto-dr-cancel?task_id=neverexisted")
    assert r.status_code == 404


def test_auto_dr_status_returns_failed_for_unknown_task():
    client = _authed_client()
    sid = client.post(
        "/api/v4/sessions", json={"question": "test research async flow"}
    ).json()["session_id"]
    r = client.get(f"/api/v4/sessions/{sid}/auto-dr-status?task_id=neverexisted")
    assert r.status_code == 200
    body = r.json()
    assert body["state"] == "failed"
    assert "neverexisted" in body["error"]


def test_track_b_endpoints_are_wired():
    """Track B has shipped — analyze/synthesize/upload routes exist (body behaviour
    is covered by test_v4_full_cycle / test_analyzer / test_synthesizer)."""
    client = _authed_client()
    sid = client.post("/api/v4/sessions", json={"question": "what drives it"}).json()["session_id"]
    # analyze with no uploads → 400 (not 501)
    r = client.post(f"/api/v4/sessions/{sid}/analyze")
    assert r.status_code == 400, r.text
    # synthesize before analyze → 400
    r = client.post(f"/api/v4/sessions/{sid}/synthesize")
    assert r.status_code == 400, r.text
    # upload-reports without files → 422 (FastAPI rejects missing multipart)
    r = client.post(f"/api/v4/sessions/{sid}/upload-reports")
    assert r.status_code == 422, r.text
    # export before final_report exists → 409
    r = client.get(f"/api/v4/sessions/{sid}/export", params={"format": "md"})
    assert r.status_code == 409, r.text


def test_long_task_status_404_for_unknown_task():
    """Polling with a bogus task_id returns 404, not silent fallthrough."""
    client = _authed_client()
    sid = client.post(
        "/api/v4/sessions", json={"question": "long-task 404 test"}
    ).json()["session_id"]
    r = client.get(
        f"/api/v4/sessions/{sid}/long-task-status",
        params={"task_id": "neverexisted"},
    )
    assert r.status_code == 404


def test_stale_synthesize_task_with_persisted_report_reaps_as_completed():
    """A restart after final_report commit must not strand/mark synthesize failed."""
    from smart_report.models import ExecutiveSummaryV4, FinalReport

    client = _authed_client()
    sid = client.post(
        "/api/v4/sessions", json={"question": "stale synthesize task test"}
    ).json()["session_id"]
    session = v4._store.get(sid)
    session.final_report = FinalReport(
        session_id=sid,
        question=session.raw_question,
        executive_summary=ExecutiveSummaryV4(main_answer="done"),
    )
    session.status = "synthesized"
    session.pending_long_tasks = [
        {
            "task_id": "stale-synth",
            "phase": "synthesize",
            "state": "running",
            "started_at": v4._now_iso(),
            "completed_at": None,
            "error": None,
            "model_preference": "opus",
        }
    ]
    v4._store.update(session)
    v4._LONG_TASK_REGISTRY.pop("stale-synth", None)

    r = client.get(
        f"/api/v4/sessions/{sid}/long-task-status",
        params={"task_id": "stale-synth"},
    )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["state"] == "completed"
    assert body["error"] is None

    r = client.get(f"/api/v4/sessions/{sid}/final-report")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["final_report"]["session_id"] == sid
    assert "source_reports" not in body


def test_concurrent_analyze_rejected_with_409(monkeypatch):
    """Submitting /analyze twice while one is in flight returns 409."""
    from smart_report import analyzer as analyzer_module
    from smart_report import intake as intake_module
    from smart_report import prompt_master as pm_module

    # Stall the analyzer LLM so the first task stays "running" while we
    # fire the second submission.
    import asyncio as _asyncio

    async def _slow_analyzer(*a, **kw):
        await _asyncio.sleep(2.0)  # long enough for second POST to arrive
        return LLMResult(
            text=json.dumps(
                {
                    "consensus": [],
                    "conflicts": [],
                    "gaps": [],
                    "followup_prompts": [],
                    "all_numeric_facts": [],
                    "all_qualitative_facts": [],
                    "high_relevance_facts": [],
                    "fact_coverage_target": 0,
                },
                ensure_ascii=False,
            ),
            cost_rub=0.0,
        )

    async def _intake_stub(*a, **kw):
        return LLMResult(
            text=json.dumps({"numeric_facts": [], "qualitative_facts": [], "claims": []}),
            cost_rub=0.0,
        )

    async def _pm_stub(*a, **kw):
        return LLMResult(
            text=json.dumps(
                {
                    "full_prompt": "X" * 250,
                    "reasoning": "r",
                    "expected_structure": ["s1"],
                    "key_entities": ["PIK"],
                    "tips_for_search": "Perplexity",
                },
                ensure_ascii=False,
            ),
            cost_rub=0.0,
        )

    monkeypatch.setattr(analyzer_module, "call_json", _slow_analyzer)
    monkeypatch.setattr(intake_module, "call_json", _intake_stub)
    monkeypatch.setattr(pm_module, "call_json", _pm_stub)

    client = _authed_client()
    sid = client.post(
        "/api/v4/sessions", json={"question": "concurrent test"}
    ).json()["session_id"]
    client.post(f"/api/v4/sessions/{sid}/generate-prompt")
    client.post(
        f"/api/v4/sessions/{sid}/upload-reports",
        files=[("files", ("a.md", b"# report a", "text/markdown"))],
    )

    r1 = client.post(f"/api/v4/sessions/{sid}/analyze")
    assert r1.status_code == 202, r1.text
    task_id_1 = r1.json()["task_id"]

    r2 = client.post(f"/api/v4/sessions/{sid}/analyze")
    assert r2.status_code == 409, r2.text
    assert task_id_1 in r2.json()["detail"]

    # Drain the first task so module-level state is clean for the next test.
    _await_long_task(client, sid, task_id_1, timeout=5.0)
