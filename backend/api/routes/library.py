import httpx
from fastapi import APIRouter, Query
from loguru import logger

from backend.config import settings

router = APIRouter()


@router.get("/library")
async def list_library(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    dataset_id: str | None = Query(default=None),
) -> dict:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            params: dict = {"page": page, "page_size": page_size}
            if dataset_id:
                url = f"{settings.ragflow_base_url}/api/v1/datasets/{dataset_id}/documents"
            else:
                url = f"{settings.ragflow_base_url}/api/v1/datasets"

            resp = await client.get(
                url,
                headers={"Authorization": f"Bearer {settings.ragflow_api_key}"},
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()

            items = data.get("data", {})
            if isinstance(items, dict):
                docs = items.get("docs", items.get("documents", []))
                total = items.get("total", len(docs))
            elif isinstance(items, list):
                docs = items
                total = len(docs)
            else:
                docs = []
                total = 0

            return {"items": docs, "total": total, "page": page, "page_size": page_size}

    except Exception as exc:
        logger.warning(f"RAGFlow library fetch failed: {exc}")
        return {"items": [], "total": 0, "page": page, "page_size": page_size}


@router.delete("/library/all")
async def clear_library() -> dict:
    dataset_ids = [
        settings.ragflow_reports_dataset_id,
        settings.ragflow_facts_dataset_id,
    ]
    cleared = 0

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            for dataset_id in dataset_ids:
                if not dataset_id:
                    continue

                list_resp = await client.get(
                    f"{settings.ragflow_base_url}/api/v1/datasets/{dataset_id}/documents",
                    headers={"Authorization": f"Bearer {settings.ragflow_api_key}"},
                    params={"page": 1, "page_size": 500},
                )
                list_resp.raise_for_status()
                data = list_resp.json().get("data", {})
                docs = data.get("docs", data.get("documents", [])) if isinstance(data, dict) else []

                for doc in docs:
                    doc_id = doc.get("id")
                    if not doc_id:
                        continue
                    resp = await client.delete(
                        f"{settings.ragflow_base_url}/api/v1/datasets/{dataset_id}/documents/{doc_id}",
                        headers={"Authorization": f"Bearer {settings.ragflow_api_key}"},
                    )
                    if resp.is_success:
                        cleared += 1
    except Exception as exc:
        logger.warning(f"RAGFlow library clear failed: {exc}")

    return {"status": "ok", "cleared": cleared}
