from __future__ import annotations

import json
import zipfile

from scripts.premium_golden_eval import evaluate_manifest, evaluate_package, evaluate_package_zip
from smart_report.exporters.premium import (
    assemble_premium_report_document,
    render_premium_docx,
    render_premium_pptx,
)
from smart_report.models import ExecutiveSummaryV4, FinalReport, Source


def _artifacts(tmp_path):
    report = FinalReport(
        session_id="golden",
        question="Should a client buy this market report?",
        executive_summary=ExecutiveSummaryV4(
            main_answer="The answer is conditional on evidence closure.",
            top_findings=["Finding one", "Finding two"],
            confidence_note="Medium.",
            what_meta_adds="Evidence gates are explicit.",
        ),
        main_synthesis="Evidence-backed synthesis.",
        all_sources=[Source(title="Source", url="https://example.com", reliability="high")],
    )
    document = assemble_premium_report_document(
        report,
        premium_readiness={
            "ready": False,
            "score": 72,
            "issues": [],
            "strengths": [],
        },
    )
    return (
        render_premium_docx(document, tmp_path / "report.docx"),
        render_premium_pptx(document, tmp_path / "deck.pptx"),
    )


def test_golden_eval_flags_blockers_when_quality_gates_are_not_ready(tmp_path):
    docx_path, pptx_path = _artifacts(tmp_path)
    audit_path = tmp_path / "audit.json"
    artifact_qa_path = tmp_path / "qa.json"
    audit_path.write_text(
        json.dumps(
            {
                "client_readiness": {"ready": False, "score": 6},
                "premium_readiness": {"ready": False, "score": 72},
                "analytic_closure": {
                    "overall_score": 35,
                    "not_closed": 1,
                    "not_started": 1,
                },
                "evidence_audit": {
                    "overall_score": 42,
                    "unsupported": 1,
                },
                "adjudication_audit": {
                    "overall_score": 35,
                    "unresolved": 1,
                    "critical_unresolved": 1,
                },
                "visual_review": {
                    "ready": False,
                    "status": "pending",
                },
                "analysis": {"high_relevance_facts": []},
                "client_report": {"all_sources": [{"url": "https://example.com"}]},
            }
        ),
        encoding="utf-8",
    )
    artifact_qa_path.write_text(
        json.dumps({"status": "blocked", "summary": {"issues": 1}}),
        encoding="utf-8",
    )

    result = evaluate_package(
        label="test",
        docx_path=docx_path,
        pptx_path=pptx_path,
        audit_json_path=audit_path,
        artifact_qa_json_path=artifact_qa_path,
    )

    assert result.overall_score < 85
    assert result.verdict == "not_acceptable"
    assert "Visual artifact QA has not passed." in result.blockers
    assert "Premium readiness gate is not ready." in result.blockers
    assert "Evidence audit has unsupported client-facing conclusions." in result.blockers
    assert "Adjudication audit has unresolved critical conflicts." in result.blockers
    assert "Manual visual review is not approved." in result.blockers


def test_golden_eval_manifest_builds_leaderboard(tmp_path):
    docx_path, pptx_path = _artifacts(tmp_path)
    audit_path = tmp_path / "audit.json"
    artifact_qa_path = tmp_path / "qa.json"
    audit_path.write_text(
        json.dumps(
            {
                "client_readiness": {"ready": True, "score": 9},
                "premium_readiness": {"ready": True, "score": 91},
                "analytic_closure": {
                    "overall_score": 92,
                    "not_closed": 0,
                    "not_started": 0,
                },
                "evidence_audit": {
                    "overall_score": 88,
                    "unsupported": 0,
                },
                "adjudication_audit": {
                    "overall_score": 86,
                    "unresolved": 0,
                    "critical_unresolved": 0,
                },
                "visual_review": {
                    "ready": True,
                    "status": "approved",
                },
                "analysis": {
                    "high_relevance_facts": [{"value": "1"} for _ in range(8)],
                },
                "client_report": {"all_sources": [{"url": "https://example.com"} for _ in range(8)]},
            }
        ),
        encoding="utf-8",
    )
    artifact_qa_path.write_text(
        json.dumps({"status": "passed", "summary": {"issues": 0}}),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "tasks": [
                    {
                        "label": "smoke-paid-ready",
                        "docx": docx_path.name,
                        "pptx": pptx_path.name,
                        "audit_json": audit_path.name,
                        "artifact_qa_json": artifact_qa_path.name,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    leaderboard = evaluate_manifest(manifest_path)

    assert leaderboard["summary"]["tasks"] == 1
    assert leaderboard["summary"]["average_score"] >= 70
    assert leaderboard["results"][0]["label"] == "smoke-paid-ready"
    assert leaderboard["results"][0]["metrics"]["artifact_qa_status"] == "passed"
    assert leaderboard["results"][0]["metrics"]["evidence_support_score"] == 88
    assert leaderboard["results"][0]["metrics"]["adjudication_score"] == 86
    assert leaderboard["results"][0]["metrics"]["visual_review_ready"] is True


def test_golden_eval_reads_premium_package_zip(tmp_path):
    docx_path, pptx_path = _artifacts(tmp_path)
    audit_path = tmp_path / "05_audit.json"
    artifact_qa_path = tmp_path / "07_artifact_qa.json"
    audit_path.write_text(
        json.dumps(
            {
                "client_readiness": {"ready": True, "score": 10},
                "premium_readiness": {"ready": True, "score": 93},
                "analytic_closure": {
                    "overall_score": 91,
                    "not_closed": 0,
                    "not_started": 0,
                },
                "evidence_audit": {
                    "overall_score": 90,
                    "unsupported": 0,
                },
                "adjudication_audit": {
                    "overall_score": 89,
                    "unresolved": 0,
                    "critical_unresolved": 0,
                },
                "visual_review": {
                    "ready": True,
                    "status": "approved",
                },
                "analysis": {
                    "high_relevance_facts": [{"value": "1"} for _ in range(8)],
                },
                "client_report": {"all_sources": [{"url": "https://example.com"} for _ in range(8)]},
            }
        ),
        encoding="utf-8",
    )
    artifact_qa_path.write_text(
        json.dumps({"status": "passed", "summary": {"issues": 0}}),
        encoding="utf-8",
    )
    package_path = tmp_path / "premium.zip"
    with zipfile.ZipFile(package_path, "w") as zf:
        zf.write(docx_path, "01_premium_report.docx")
        zf.write(pptx_path, "02_premium_deck.pptx")
        zf.write(audit_path, "05_audit.json")
        zf.write(artifact_qa_path, "07_artifact_qa.json")

    result = evaluate_package_zip(label="zip", package_zip_path=package_path)

    assert result.metrics["premium_ready"] is True
    assert result.metrics["visual_review_ready"] is True
    assert result.verdict in {"paid_client_ready", "borderline_paid_ready"}
