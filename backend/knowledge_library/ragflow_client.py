from __future__ import annotations

import json
from typing import Any

import httpx
from loguru import logger

from backend.config import settings
from backend.schemas.knowledge_unit import KnowledgeUnit, LibraryHit, SourceRecord
from backend.utils.retry import api_retry

try:  # pragma: no cover - optional dependency
    from ragflow_sdk import RAGFlow as _RAGFlowSDK
except ImportError:  # pragma: no cover - optional dependency
    _RAGFlowSDK = None


class RAGFlowClient:
    def __init__(self) -> None:
        self.base_url = settings.ragflow_base_url.rstrip("/")
        self.api_key = settings.ragflow_api_key
        self._sdk = None
        self._dataset_id_cache: dict[str, str] = {}

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _sdk_client(self):
        if _RAGFlowSDK is None:
            return None
        if self._sdk is None:
            self._sdk = _RAGFlowSDK(api_key=self.api_key, base_url=self.base_url)
        return self._sdk

    async def _request(self, method: str, path: str, **kwargs) -> dict[str, Any]:
        extra_headers = kwargs.pop("headers", {})
        headers = {**self._headers(), **extra_headers}
        if "json" in kwargs and "files" not in kwargs:
            has_content_type = any(k.lower() == "content-type" for k in headers.keys())
            if not has_content_type:
                headers["Content-Type"] = "application/json"

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.request(
                method,
                f"{self.base_url}{path}",
                headers=headers,
                **kwargs,
            )
            response.raise_for_status()
            payload = response.json()

        if isinstance(payload, dict):
            code = payload.get("code")
            if code is not None and code != 0:
                message = payload.get("message") or payload.get("error") or "unknown error"
                raise RuntimeError(f"RAGFlow API error code={code}: {message}")
            return payload
        return {"data": payload}

    async def _upload_text_document(
        self,
        *,
        dataset_id: str,
        name: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        uploaded = await self._request(
            "POST",
            f"/api/v1/datasets/{dataset_id}/documents",
            files={"file": (name, content.encode("utf-8"), "text/markdown")},
        )
        raw_data = uploaded.get("data")
        document_id = ""
        if isinstance(raw_data, list) and raw_data:
            document_id = str(raw_data[0].get("id", ""))
        elif isinstance(raw_data, dict):
            document_id = str((raw_data.get("document") or {}).get("id", ""))

        if document_id and metadata:
            await self._request(
                "PUT",
                f"/api/v1/datasets/{dataset_id}/documents/{document_id}",
                json={
                    "name": name,
                    "meta_fields": metadata,
                },
            )

        return document_id

    async def _list_datasets(self) -> list[dict[str, Any]]:
        data = await self._request("GET", "/api/v1/datasets", params={"page": 1, "page_size": 200})
        items = data.get("data", {})
        if isinstance(items, dict):
            return items.get("docs", items.get("datasets", []))
        if isinstance(items, list):
            return items
        return []

    async def _resolve_dataset_id(self, kind: str) -> str:
        if kind in self._dataset_id_cache:
            return self._dataset_id_cache[kind]

        if kind == "reports":
            configured_id = settings.ragflow_reports_dataset_id
            dataset_name = settings.ragflow_reports_dataset_name
        else:
            configured_id = settings.ragflow_facts_dataset_id
            dataset_name = settings.ragflow_facts_dataset_name

        if configured_id:
            self._dataset_id_cache[kind] = configured_id
            return configured_id

        datasets = await self._list_datasets()
        for dataset in datasets:
            if str(dataset.get("name", "")).strip().lower() == dataset_name.strip().lower():
                dataset_id = str(dataset.get("id", ""))
                if dataset_id:
                    self._dataset_id_cache[kind] = dataset_id
                    logger.info(f"Resolved RagFlow {kind} dataset id by name: {dataset_name} -> {dataset_id}")
                    return dataset_id

        logger.warning(f"RAGFlow {kind} dataset not found by name: {dataset_name}")
        return ""

    @api_retry()
    async def search(
        self,
        query: str,
        dataset_id: str | None = None,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        payload = {
            "question": query,
            "dataset_ids": [dataset_id] if dataset_id else [],
            "top_k": top_k,
        }
        data = await self._request("POST", "/api/v1/retrieval", json=payload)
        data_block = data.get("data")
        if isinstance(data_block, dict):
            return data_block.get("chunks", [])
        return []

    @api_retry()
    async def search_similar_reports(
        self,
        query: str,
        threshold: float = 0.85,
    ) -> LibraryHit | None:
        dataset_id = await self._resolve_dataset_id("reports") or None
        chunks = await self.search(query, dataset_id=dataset_id, top_k=5)

        best_chunk = None
        best_score = -1.0
        for chunk in chunks:
            similarity = float(chunk.get("similarity", 0.0))
            if similarity > best_score:
                best_chunk = chunk
                best_score = similarity

        if not best_chunk or best_score < threshold:
            return None

        return LibraryHit(
            report_id=best_chunk.get("document_id", ""),
            title=best_chunk.get("document_name") or best_chunk.get("document_keyword", ""),
            similarity=best_score,
            summary=best_chunk.get("content", "")[:500],
            session_id=best_chunk.get("metadata", {}).get("session_id", ""),
            dataset_id=dataset_id or "",
        )

    @api_retry()
    async def save_report(
        self,
        session_id: str | Any,
        title: str | None = None,
        content: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        # Backward-compatible paths:
        #   save_report(report_obj, session_id)
        #   save_report(report_obj, session_id, metadata)
        if not isinstance(session_id, str) and title is not None and (
            content is None or isinstance(content, dict)
        ):
            report = session_id
            actual_session_id = title
            payload = report.model_dump(mode="json") if hasattr(report, "model_dump") else {}
            extra_metadata = content if isinstance(content, dict) else metadata
            return await self.save_report(
                actual_session_id,
                payload.get("title", f"report_{actual_session_id}"),
                json.dumps(payload, ensure_ascii=False, default=str),
                {"session_id": actual_session_id, **(extra_metadata or {})},
            )

        if not isinstance(session_id, str):
            raise TypeError("session_id must be a string")

        dataset_id = await self._resolve_dataset_id("reports")
        if not dataset_id:
            logger.warning("ragflow_reports_dataset_id not set, skipping report save")
            return ""

        body = {
            "session_id": session_id,
            "title": title or "",
            **(metadata or {}),
        }
        doc_name = f"report_{session_id}.md"
        doc_id = await self._upload_text_document(
            dataset_id=dataset_id,
            name=doc_name,
            content=content or "",
            metadata=body,
        )
        if doc_id:
            await self._request(
                "POST",
                f"/api/v1/datasets/{dataset_id}/chunks",
                json={"document_ids": [doc_id]},
            )
        return doc_id

    @api_retry()
    async def save_facts(self, facts: list[KnowledgeUnit]) -> None:
        dataset_id = await self._resolve_dataset_id("facts")
        if not dataset_id or not facts:
            return

        verified_facts = [
            fact for fact in facts if getattr(fact, "verification_status", "VERIFIED") == "VERIFIED"
        ]
        uploaded_doc_ids: list[str] = []
        for fact in verified_facts:
            metadata = {
                "source_url": fact.source_url or fact.source,
                "reliability_score": fact.confidence,
                "topic_tags": fact.tags,
                "verification_status": fact.verification_status,
                "category": fact.category,
            }
            doc_id = await self._upload_text_document(
                dataset_id=dataset_id,
                name=f"fact_{fact.id}.md",
                content=fact.content,
                metadata=metadata,
            )
            if doc_id:
                uploaded_doc_ids.append(doc_id)

        if uploaded_doc_ids:
            await self._request(
                "POST",
                f"/api/v1/datasets/{dataset_id}/chunks",
                json={"document_ids": uploaded_doc_ids},
            )

    @api_retry()
    async def get_sources(self, topic_tags: list[str]) -> list[SourceRecord]:
        dataset_id = await self._resolve_dataset_id("reports")
        if not dataset_id:
            return []

        data = await self._request(
            "GET",
            f"/api/v1/datasets/{dataset_id}/documents",
            params={"page": 1, "page_size": 100},
        )
        docs = data.get("data", {}).get("docs", [])
        matched: list[SourceRecord] = []
        requested_tags = set(topic_tags)

        for doc in docs:
            metadata = doc.get("metadata", {}) or {}
            doc_tags = set(metadata.get("topic_tags", []) or [])
            if requested_tags and not (requested_tags & doc_tags):
                continue
            matched.append(
                SourceRecord(
                    url=metadata.get("url") or metadata.get("source_url", ""),
                    title=doc.get("name", ""),
                    domain=metadata.get("domain", ""),
                    reliability_score=float(metadata.get("reliability_score", 0.5)),
                    topic_tags=list(doc_tags),
                    document_id=doc.get("id", ""),
                )
            )

        return matched

    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(
                    f"{self.base_url}/v1/system/version",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                return resp.status_code == 200
        except Exception:
            return False


ragflow = RAGFlowClient()
