import json

import httpx
from langsmith import traceable
from loguru import logger

from backend.config import settings
from backend.pipeline.model_router import AgentTask, get_model, estimate_cost
from backend.pipeline.state import AgentState
from backend.schemas.research_result import ParallelBatches, QueryBatch
from backend.utils.json_parse import parse_llm_json, supports_json_mode
from backend.utils.retry import llm_retry

MAX_QUERIES_DEV = 3

SYSTEM_PROMPT = """\
You are the Supervisor agent. You receive a list of research queries and must decide \
the optimal execution strategy: which queries can run in parallel and which must run sequentially.

Rules:
- Queries that are independent of each other → parallel batch.
- Queries where one depends on the result of another → sequential (separate batches, ordered).
- Group related parallel queries into the same batch.
- Minimize total batches to reduce latency.

Return strictly valid JSON matching this schema:
{
  "batches": [
    {
      "queries": ["query1", "query2"],
      "mode": "parallel",
      "rationale": "These queries are independent market segments"
    }
  ],
  "total_queries": 5,
  "strategy_rationale": "Overall strategy explanation"
}
"""


@llm_retry()
async def _plan_batches(queries: list[str], model: str) -> str:
    user_content = "Plan execution strategy for these research queries:\n\n" + "\n".join(
        f"{i+1}. {q}" for i, q in enumerate(queries)
    )
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{settings.openrouter_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                "temperature": 0.1,
                **( {"response_format": {"type": "json_object"}} if supports_json_mode(model) else {} ),
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


@traceable(name="supervisor_agent")
async def run_supervisor(state: AgentState) -> dict:
    """Plan research strategy: decide parallel vs sequential batches."""
    logger.info("Supervisor agent started")

    splitter_msg = next(
        (m for m in state.get("messages", []) if m["role"] == "prompt_splitter"),
        None,
    )
    master = state.get("master_prompt")

    if splitter_msg:
        data_queries = [
            q.strip()
            for q in splitter_msg["content"].split("\n---\n")
            if q.strip()
        ]
    elif master:
        data_queries = [master.user_prompt]
    else:
        data_queries = [state.get("user_request", {}).get("query", "")]

    if settings.dev_mode and len(data_queries) > MAX_QUERIES_DEV:
        data_queries = data_queries[:MAX_QUERIES_DEV]
        logger.info(f"[DEV] Capped supervisor queries to {MAX_QUERIES_DEV}")

    if len(data_queries) <= 1:
        batches = ParallelBatches(
            batches=[QueryBatch(queries=data_queries, mode="parallel", rationale="Single query")],
            total_queries=len(data_queries),
            strategy_rationale="Single query, no splitting needed",
        )
        cost = 0.0
    else:
        model = get_model(AgentTask.SUPERVISION)
        raw = await _plan_batches(data_queries, model)
        try:
            parsed = parse_llm_json(raw, context="supervisor")
            batches = ParallelBatches(**parsed)
        except (ValueError, Exception) as exc:
            logger.warning(f"Supervisor parse failed, using default batching: {exc}")
            batches = ParallelBatches(
                batches=[QueryBatch(queries=data_queries, mode="parallel", rationale="fallback")],
                total_queries=len(data_queries),
                strategy_rationale="Fallback: parse error",
            )
        cost = estimate_cost(AgentTask.SUPERVISION, sum(len(q) for q in data_queries) // 4, len(raw) // 4)

    iteration = state.get("iteration", 0) + 1
    logger.info(
        f"Supervisor planned {batches.total_queries} queries in {len(batches.batches)} batches "
        f"(iteration {iteration})"
    )

    return {
        "data_queries": data_queries,
        "parallel_batches": batches,
        "revision_count": 0,
        "current_agent": "supervisor",
        "status": "researching",
        "iteration": iteration,
        "max_iterations": state.get("max_iterations", 3),
        "cost_usd": state.get("cost_usd", 0.0) + cost,
    }
