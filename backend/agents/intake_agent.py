import json
import re
from pathlib import Path

import httpx
from loguru import logger

from backend.config import settings
from backend.knowledge_library.ragflow_client import ragflow
from backend.pipeline.model_router import AgentTask, get_model, estimate_cost
from backend.pipeline.state import AgentState
from backend.schemas.intake import IntakeResult, SimilarReport
from backend.utils.json_parse import parse_llm_json, supports_json_mode
from backend.utils.retry import llm_retry

BUDGET_MAP: dict[str, float] = {
    "light": settings.budget_light,
    "standard": settings.budget_standard,
    "deep": settings.budget_deep,
    "exhaustive": settings.budget_exhaustive,
}


def _load_prompt(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.warning(f"Prompt file not found: {path}, using default")
        return (
            "You are an intake analyst. Parse the user request and return JSON with "
            "ALL of these exact fields (no extras, no omissions):\n"
            '{"original_query": "<exact user query>", '
            '"cleaned_query": "<normalised query>", '
            '"intent": "research|analysis|comparison|overview|deep_dive|forecast", '
            '"domain": "finance|tech|healthcare|energy|retail|general", '
            '"complexity": "low|medium|high", '
            '"depth": "light|standard|deep|exhaustive", '
            '"key_entities": ["entity1"], '
            '"clarifying_questions": [], '
            '"language": "ru"}'
        )


@llm_retry()
async def _call_llm(system_prompt: str, user_message: str, model: str) -> str:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "temperature": 0.2,
    }
    if supports_json_mode(model):
        payload["response_format"] = {"type": "json_object"}

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{settings.openrouter_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


def _fallback_intake(query: str) -> IntakeResult:
    language = "ru" if re.search(r"[А-Яа-яЁё]", query) else "en"
    cleaned = " ".join(query.split())
    return IntakeResult(
        original_query=query,
        cleaned_query=cleaned or query,
        intent="analysis",
        domain="general",
        complexity="medium",
        depth="standard",
        key_entities=[],
        clarifying_questions=[],
        language=language,
    )


async def _search_similar_reports(query: str) -> list[SimilarReport]:
    try:
        if not settings.ragflow_api_key:
            logger.debug("RAGFlow API key not configured, skipping similarity search")
            return []

        reports_dataset_id = await ragflow._resolve_dataset_id("reports")
        if not reports_dataset_id:
            return []
        chunks = await ragflow.search(query=query, dataset_id=reports_dataset_id, top_k=5)
        return [
            SimilarReport(
                chunk_id=chunk.get("chunk_id", chunk.get("id", "")),
                content=chunk.get("content", "")[:500],
                score=chunk.get("similarity", 0.0),
                document_name=chunk.get("document_name", ""),
            )
            for chunk in chunks
        ]
    except Exception as e:
        logger.warning(f"RAGFlow similarity search failed: {e}")
        return []


async def run_intake(state: AgentState) -> dict:
    logger.info("Intake agent started")
    model = get_model(AgentTask.INTAKE)
    user_request = state["user_request"]
    query = user_request.get("query", "")
    selected_depth = state.get("selected_depth")

    system_prompt = _load_prompt("prompts/intake_system.txt")

    similar_reports = await _search_similar_reports(query)

    user_message = query
    if similar_reports:
        similar_context = json.dumps(
            [{"title": r.document_name, "score": r.score, "snippet": r.content[:200]} for r in similar_reports],
            ensure_ascii=False,
        )
        user_message = (
            f"{query}\n\n"
            f"[CONTEXT] Similar reports found in knowledge library:\n{similar_context}"
        )

    raw = await _call_llm(system_prompt, user_message, model)
    try:
        parsed = parse_llm_json(raw, context="intake_agent")
        result = IntakeResult.model_validate(parsed)
    except Exception as exc:
        logger.warning(f"Intake parse failed, using heuristic fallback: {exc}")
        result = _fallback_intake(query)

    if len(result.clarifying_questions) > 5:
        result.clarifying_questions = result.clarifying_questions[:5]

    result.similar_reports = similar_reports

    depth = selected_depth if selected_depth in BUDGET_MAP else result.depth
    depth = depth if depth in BUDGET_MAP else "standard"
    result.depth = depth
    result.budget_limit = BUDGET_MAP[depth]

    cost = estimate_cost(AgentTask.INTAKE, len(user_message) // 4, len(raw) // 4)
    logger.info(
        f"Intake complete: intent={result.intent}, domain={result.domain}, "
        f"depth={result.depth}, budget=${result.budget_limit:.2f}, "
        f"similar_reports={len(similar_reports)}"
    )

    return {
        "intake_result": result,
        "cost_usd": state.get("cost_usd", 0) + cost,
        "current_agent": "intake",
        "status": "prompting",
    }
