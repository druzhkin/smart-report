from __future__ import annotations

import httpx
import pytest
import respx

from backend.schemas.report_schema import ReportOutput, ReportStatus
from backend.schemas.knowledge_unit import KnowledgeUnit


@pytest.fixture
def ragflow_client(monkeypatch):
    from backend.knowledge_library.ragflow_client import RAGFlowClient
    from backend.config import settings

    monkeypatch.setattr(settings, "ragflow_base_url", "http://localhost:9380")
    monkeypatch.setattr(settings, "ragflow_api_key", "test-key")
    monkeypatch.setattr(settings, "ragflow_reports_dataset_id", "reports-ds")
    monkeypatch.setattr(settings, "ragflow_facts_dataset_id", "facts-ds")
    monkeypatch.setattr(settings, "ragflow_reports_dataset_name", "smart-report-reports")
    monkeypatch.setattr(settings, "ragflow_facts_dataset_name", "smart-report-facts")
    return RAGFlowClient()


@pytest.mark.asyncio
async def test_search_returns_hit_above_threshold(ragflow_client):
    with respx.mock:
        respx.post("http://localhost:9380/api/v1/retrieval").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "chunks": [
                            {
                                "document_id": "doc-1",
                                "document_name": "AI Market Report",
                                "similarity": 0.91,
                                "content": "Summary",
                                "metadata": {"session_id": "sess-1"},
                            }
                        ]
                    }
                },
            )
        )
        hit = await ragflow_client.search_similar_reports("AI chips", threshold=0.85)

    assert hit is not None
    assert hit.report_id == "doc-1"
    assert hit.title == "AI Market Report"
    assert hit.similarity == pytest.approx(0.91)


@pytest.mark.asyncio
async def test_search_returns_none_below_threshold(ragflow_client):
    with respx.mock:
        respx.post("http://localhost:9380/api/v1/retrieval").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "chunks": [
                            {
                                "document_id": "doc-2",
                                "document_name": "Weak Match",
                                "similarity": 0.62,
                                "content": "Summary",
                            }
                        ]
                    }
                },
            )
        )
        hit = await ragflow_client.search_similar_reports("AI chips", threshold=0.85)

    assert hit is None


@pytest.mark.asyncio
async def test_save_report_returns_document_id(ragflow_client):
    with respx.mock:
        upload_route = respx.post("http://localhost:9380/api/v1/datasets/reports-ds/documents").mock(
            return_value=httpx.Response(
                200,
                json={"code": 0, "data": [{"id": "report-doc-123"}]},
            )
        )
        update_route = respx.put(
            "http://localhost:9380/api/v1/datasets/reports-ds/documents/report-doc-123"
        ).mock(return_value=httpx.Response(200, json={"code": 0}))
        parse_route = respx.post("http://localhost:9380/api/v1/datasets/reports-ds/chunks").mock(
            return_value=httpx.Response(200, json={"code": 0})
        )
        document_id = await ragflow_client.save_report(
            "session-1",
            "AI Market Report",
            "# Title\nBody",
            {"region": "RU"},
        )

    assert upload_route.called
    assert update_route.called
    assert parse_route.called
    assert document_id == "report-doc-123"


@pytest.mark.asyncio
async def test_save_facts_filters_non_verified(ragflow_client):
    verified = KnowledgeUnit(
        id="fact-1",
        content="Verified fact",
        source="https://example.com/1",
        source_url="https://example.com/1",
        category="fact",
        confidence=0.9,
        tags=["ai", "chips"],
        verification_status="VERIFIED",
    )
    rejected = KnowledgeUnit(
        id="fact-2",
        content="Rejected fact",
        source="https://example.com/2",
        source_url="https://example.com/2",
        category="fact",
        confidence=0.4,
        tags=["ai"],
        verification_status="REJECTED",
    )

    with respx.mock:
        upload_route = respx.post("http://localhost:9380/api/v1/datasets/facts-ds/documents").mock(
            return_value=httpx.Response(
                200,
                json={"code": 0, "data": [{"id": "fact-doc-1"}]},
            )
        )
        update_route = respx.put(
            "http://localhost:9380/api/v1/datasets/facts-ds/documents/fact-doc-1"
        ).mock(return_value=httpx.Response(200, json={"code": 0}))
        parse_route = respx.post("http://localhost:9380/api/v1/datasets/facts-ds/chunks").mock(
            return_value=httpx.Response(200, json={"code": 0})
        )
        await ragflow_client.save_facts([verified, rejected])

    assert upload_route.call_count == 1
    assert update_route.call_count == 1
    assert parse_route.call_count == 1
    upload_payload = upload_route.calls[0].request.content.decode("utf-8", errors="ignore")
    assert "Verified fact" in upload_payload
    assert "Rejected fact" not in upload_payload


@pytest.mark.asyncio
async def test_save_report_resolves_dataset_id_by_name(monkeypatch):
    from backend.knowledge_library.ragflow_client import RAGFlowClient
    from backend.config import settings

    monkeypatch.setattr(settings, "ragflow_base_url", "http://localhost:9380")
    monkeypatch.setattr(settings, "ragflow_api_key", "test-key")
    monkeypatch.setattr(settings, "ragflow_reports_dataset_id", "")
    monkeypatch.setattr(settings, "ragflow_facts_dataset_id", "")
    monkeypatch.setattr(settings, "ragflow_reports_dataset_name", "smart-report-reports")
    monkeypatch.setattr(settings, "ragflow_facts_dataset_name", "smart-report-facts")
    client = RAGFlowClient()

    with respx.mock:
        list_route = respx.get("http://localhost:9380/api/v1/datasets").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "datasets": [
                            {"id": "reports-ds", "name": "smart-report-reports"},
                            {"id": "facts-ds", "name": "smart-report-facts"},
                        ]
                    }
                },
            )
        )
        save_route = respx.post("http://localhost:9380/api/v1/datasets/reports-ds/documents").mock(
            return_value=httpx.Response(
                200,
                json={"code": 0, "data": [{"id": "report-doc-456"}]},
            )
        )
        update_route = respx.put(
            "http://localhost:9380/api/v1/datasets/reports-ds/documents/report-doc-456"
        ).mock(return_value=httpx.Response(200, json={"code": 0}))
        parse_route = respx.post("http://localhost:9380/api/v1/datasets/reports-ds/chunks").mock(
            return_value=httpx.Response(200, json={"code": 0})
        )
        document_id = await client.save_report(
            "session-2",
            "Resolved Dataset Report",
            "# Title\nBody",
            {"region": "RU"},
        )

    assert list_route.called
    assert save_route.called
    assert update_route.called
    assert parse_route.called
    assert document_id == "report-doc-456"


@pytest.mark.asyncio
async def test_save_report_accepts_report_object_with_metadata(ragflow_client):
    report = ReportOutput(
        title="AI Report",
        executive_summary="Summary",
        sections=[],
        status=ReportStatus.COMPLETED,
    )

    with respx.mock:
        route = respx.post("http://localhost:9380/api/v1/datasets/reports-ds/documents").mock(
            return_value=httpx.Response(
                200,
                json={"code": 0, "data": [{"id": "report-doc-789"}]},
            )
        )
        update_route = respx.put(
            "http://localhost:9380/api/v1/datasets/reports-ds/documents/report-doc-789"
        ).mock(return_value=httpx.Response(200, json={"code": 0}))
        parse_route = respx.post("http://localhost:9380/api/v1/datasets/reports-ds/chunks").mock(
            return_value=httpx.Response(200, json={"code": 0})
        )
        document_id = await ragflow_client.save_report(
            report,
            "session-3",
            {"qa_verdict": "REJECT", "status": "failed"},
        )

    assert route.called
    assert update_route.called
    assert parse_route.called
    upload_payload = route.calls[0].request.content.decode("utf-8", errors="ignore")
    assert "AI Report" in upload_payload
    update_payload = update_route.calls[0].request.content.decode("utf-8")
    assert "qa_verdict" in update_payload
    assert "failed" in update_payload
    assert document_id == "report-doc-789"
