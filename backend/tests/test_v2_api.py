from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

from backend.main import app
from backend.v2.intake import build_clarification_pack, build_request_spec
from backend.v2.repository import FileRunRepository


def test_clarification_pack_uses_readable_russian_text() -> None:
    request_spec = build_request_spec("Сравни платформы для аналитического отчёта по рынку", depth="standard")
    pack = build_clarification_pack("ru-run", request_spec)

    prompts = [question.prompt for question in pack.questions]
    assert any("Какое конкретное решение" in prompt for prompt in prompts)
    assert not any("РљР°РєРѕРµ" in prompt for prompt in prompts)


def test_v2_report_flow_end_to_end(tmp_path: Path, monkeypatch) -> None:
    from backend.api.routes import reports as reports_route

    test_repo = FileRunRepository(root=str(tmp_path / "runs"), reports_root=str(tmp_path / "reports"))
    monkeypatch.setattr(reports_route, "repo", test_repo)
    reports_route._live_queues.clear()
    reports_route._live_tasks.clear()

    with TestClient(app) as client:
        create_response = client.post(
            "/api/reports",
            json={
                "request": "Evaluate LLM observability platforms for an enterprise document workflow product.",
                "depth": "standard",
                "output_formats": ["html", "pdf", "docx"],
            },
        )
        assert create_response.status_code == 200
        create_payload = create_response.json()
        run_id = create_payload["session_id"]
        assert create_payload["status"] == "awaiting_scope"
        assert create_payload["request_spec"]["report_type"] == "vendor_evaluation"

        clarify_response = client.post(f"/api/reports/{run_id}/clarify")
        assert clarify_response.status_code == 200
        clarification_fields = [question["field"] for question in clarify_response.json()["questions"]]
        assert clarification_fields == ["decision_context", "evaluation_dimensions", "geography", "budget"]

        scope_response = client.post(
            f"/api/reports/{run_id}/scope",
            json={
                "answers": {
                    "decision-context": "Choose an observability stack for a privacy-sensitive product launch.",
                    "geography": "global",
                }
            },
        )
        assert scope_response.status_code == 200
        assert scope_response.json()["status"] == "running"

        deadline = time.time() + 8
        final_payload = None
        while time.time() < deadline:
            response = client.get(f"/api/reports/{run_id}")
            assert response.status_code == 200
            payload = response.json()
            if payload["status"] in {"completed", "failed"}:
                final_payload = payload
                break
            time.sleep(0.1)

        assert final_payload is not None
        assert final_payload["status"] == "completed"
        assert final_payload["analysis_brief"] is not None
        assert final_payload["coverage_report"] is not None
        assert final_payload["audit_summary"]["release_status"] in {"released", "blocked"}
        assert "html" in final_payload["report_urls"]

        evidence_response = client.get(f"/api/reports/{run_id}/evidence")
        sources_response = client.get(f"/api/reports/{run_id}/sources")
        artifacts_response = client.get(f"/api/reports/{run_id}/artifacts")

        assert evidence_response.status_code == 200
        assert sources_response.status_code == 200
        assert artifacts_response.status_code == 200
        assert evidence_response.json()["claim_table"]
        assert sources_response.json()["sources"]
        assert "report.md" in artifacts_response.json()["package_files"]
