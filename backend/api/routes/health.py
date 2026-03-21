import httpx
from fastapi import APIRouter
from loguru import logger

from backend.config import settings
from backend.knowledge_library.ragflow_client import ragflow

router = APIRouter()


async def _check_openrouter() -> str:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(
                f"{settings.openrouter_base_url}/models",
                headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
            )
            return "ok" if resp.status_code == 200 else "error"
    except Exception as exc:
        logger.warning(f"OpenRouter health check failed: {exc}")
        return "error"


async def _check_perplexity() -> str:
    if not settings.perplexity_api_key:
        return "not_configured"
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(
                "https://api.perplexity.ai/models",
                headers={"Authorization": f"Bearer {settings.perplexity_api_key}"},
            )
            return "ok" if resp.status_code in (200, 404) else "error"
    except Exception as exc:
        logger.warning(f"Perplexity health check failed: {exc}")
        return "error"



@router.get("/health")
async def health_check() -> dict:
    openrouter_status, perplexity_status, ragflow_status = await _check_openrouter(), await _check_perplexity(), "ok" if await ragflow.health() else "error"

    overall = "ok" if openrouter_status == "ok" else "degraded"

    return {
        "status": overall,
        "models": {
            "openrouter": openrouter_status,
            "perplexity": perplexity_status,
            "ragflow": ragflow_status,
        },
    }
