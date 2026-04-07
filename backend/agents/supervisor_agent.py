from __future__ import annotations

import asyncio
import json

import httpx
from langsmith import traceable
from loguru import logger

from backend.config import settings
from backend.knowledge_library.retriever import retriever
from backend.pipeline.model_router import AgentTask, estimate_cost, get_model
from backend.pipeline.state import AgentState
from backend.schemas.research_result import (
    ParallelBatches,
    QueryBatch,
    ResearchBranchState,
    ResearchTask,
    TaskDecomposition,
)
from backend.utils.json_parse import parse_llm_json, supports_json_mode
from backend.utils.retry import llm_retry

MAX_QUERIES_DEV = 3
MAX_TASK_QUESTION_LEN = 240

SYSTEM_PROMPT = """\
You are the Research Orchestrator. You receive a structured task decomposition and must decide
the optimal execution strategy for research tasks.

Rules:
- Tasks with no dependencies and different evidence needs may run in parallel.
- Tasks that depend on prior outputs must run sequentially.
- Keep related tasks grouped when it improves retrieval context.
- Minimize batches without sacrificing correctness.

Return strictly valid JSON:
{
  "batches": [
    {
      "queries": ["task question 1", "task question 2"],
      "mode": "parallel",
      "rationale": "Why these tasks can run together"
    }
  ],
  "total_queries": 3,
  "strategy_rationale": "Overall orchestration strategy"
}
"""


def _parse_splitter_payload(state: AgentState) -> TaskDecomposition | None:
    payload = state.get("task_decomposition")
    if payload:
        return payload

    splitter_msg = next(
        (m for m in state.get("messages", []) if m["role"] == "prompt_splitter"),
        None,
    )
    if not splitter_msg:
        return None

    try:
        parsed = parse_llm_json(splitter_msg["content"], context="prompt_splitter")
        return TaskDecomposition(**parsed)
    except Exception:
        raw_queries = [
            q.strip()
            for q in splitter_msg["content"].split("\n---\n")
            if q.strip()
        ]
        if not raw_queries:
            return None
        return TaskDecomposition(
            main_question=raw_queries[0],
            subquestions=[
                ResearchTask(id=f"task-{idx+1}", question=query, priority=1)
                for idx, query in enumerate(raw_queries)
            ],
        )


@llm_retry()
async def _plan_batches(tasks: list[dict], model: str) -> str:
    user_content = json.dumps({"tasks": tasks}, ensure_ascii=False)
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
                **({"response_format": {"type": "json_object"}} if supports_json_mode(model) else {}),
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


async def _attach_source_strategy(tasks: list[ResearchTask]) -> list[ResearchTask]:
    async def _strategy_for(task: ResearchTask) -> str:
        hits = await retriever.retrieve(
            task.question,
            use_ragflow=bool(settings.ragflow_api_key),
            top_k=3,
        )
        if not hits:
            return "web"
        top_sources = {hit.get("source", "") for hit in hits}
        if top_sources == {"ragflow"}:
            return "ragflow"
        return "hybrid"

    strategies = await asyncio.gather(*[_strategy_for(task) for task in tasks])
    updated: list[ResearchTask] = []
    for task, strategy in zip(tasks, strategies):
        updated.append(task.model_copy(update={"source_strategy": strategy}))
    return updated


def _fallback_batches(tasks: list[ResearchTask]) -> ParallelBatches:
    independent = [task.question for task in tasks if not task.depends_on]
    dependent = [task.question for task in tasks if task.depends_on]
    batches: list[QueryBatch] = []

    if independent:
        batches.append(
            QueryBatch(
                queries=independent,
                mode="parallel" if len(independent) > 1 else "sequential",
                rationale="Independent tasks can be explored without upstream context.",
            )
        )
    for query in dependent:
        batches.append(
            QueryBatch(
                queries=[query],
                mode="sequential",
                rationale="This task depends on prior evidence and should execute after upstream tasks.",
            )
        )

    return ParallelBatches(
        batches=batches or [QueryBatch(queries=[task.question for task in tasks], mode="parallel", rationale="fallback")],
        total_queries=len(tasks),
        strategy_rationale="Dependency-aware fallback orchestration",
    )


def _merge_follow_up_tasks(tasks: list[ResearchTask], extra_queries: list[str]) -> list[ResearchTask]:
    def _clean_query(query: str) -> str:
        compact = " ".join((query or "").split()).strip()
        if len(compact) > MAX_TASK_QUESTION_LEN:
            compact = compact[: MAX_TASK_QUESTION_LEN - 1].rstrip() + "…"
        return compact

    existing_questions = {task.question for task in tasks}
    next_priority = max((task.priority for task in tasks), default=1) + 1
    merged = list(tasks)
    for index, query in enumerate(extra_queries, start=1):
        normalized = _clean_query(query)
        if not normalized or normalized in existing_questions:
            continue
        if len(normalized) < 20:
            continue
        merged.append(
            ResearchTask(
                id=f"follow-up-{index}",
                question=normalized,
                priority=next_priority,
                rationale="Follow-up query generated from reflection/critique.",
            )
        )
        existing_questions.add(normalized)
    return merged


def _build_branch_states(state: AgentState, tasks: list[ResearchTask]) -> list[ResearchBranchState]:
    results = list(state.get("research_results", []) or [])
    evidence_items = list(state.get("evidence_items", []) or [])
    previous_states = {
        branch.question: branch
        for branch in list(state.get("branch_states", []) or [])
    }
    result_by_query = {result.query: result for result in results}
    current_iteration = state.get("iteration", 0)
    contradiction_log = list(state.get("contradiction_log", []) or [])

    branch_states: list[ResearchBranchState] = []
    for task in tasks:
        previous = previous_states.get(task.question)
        result = result_by_query.get(task.question)
        matched_evidence = [
            item for item in evidence_items
            if task.question.lower() in item.claim.lower() or task.question.lower() in item.snippet.lower()
        ]
        source_domains = sorted({
            source.domain
            for source in (result.sources if result else [])
            if source.domain
        })

        if result is None:
            status = "pending"
            confidence = previous.confidence if previous else 0.0
            gaps = list(previous.gaps) if previous else []
            source_count = previous.source_count if previous else 0
        else:
            weak_sources = len(result.sources) < 2
            status = "needs_follow_up" if weak_sources or result.gaps else "completed"
            if previous and previous.status == "completed":
                status = "completed"
            confidence = result.confidence
            gaps = list(result.gaps)
            source_count = len(result.sources)

        if task.depends_on:
            dep_statuses = [
                next((branch.status for branch in branch_states if branch.task_id == dep_id), "pending")
                for dep_id in task.depends_on
            ]
            if any(dep_status != "completed" for dep_status in dep_statuses) and result is None:
                status = "blocked"

        follow_up_queries: list[str] = []
        if status == "needs_follow_up":
            follow_up_queries.append(f"Find stronger evidence for: {task.question}")
        if previous and previous.follow_up_queries:
            follow_up_queries = previous.follow_up_queries + follow_up_queries
        contradiction_notes = [
            entry.get("reason", "")
            for entry in contradiction_log
            if task.question.lower() in " ".join(entry.get("claims", [])).lower()
            or task.question.lower() in entry.get("topic", "").lower()
        ]

        next_action = "deepen"
        action_reason = "Initial branch has not been explored yet."
        if status == "completed":
            next_action = "complete"
            action_reason = "Branch is sufficiently covered for the current cycle."
        elif status == "blocked":
            next_action = "hold"
            action_reason = "This branch depends on upstream work that is not completed yet."
        elif status == "needs_follow_up":
            if contradiction_notes:
                next_action = "verify"
                action_reason = "Contradictory evidence was detected for this branch."
            elif gaps:
                next_action = "verify"
                action_reason = "Branch has explicit research gaps that require verification."
            elif source_count < 2:
                next_action = "widen"
                action_reason = "Branch needs more independent sources before synthesis."
            elif confidence < 0.65:
                next_action = "deepen"
                action_reason = "Branch needs deeper evidence before synthesis."
            else:
                next_action = "verify"
                action_reason = "Branch should be validated before being treated as complete."

        branch_states.append(
            ResearchBranchState(
                task_id=task.id,
                question=task.question,
                status=status,
                next_action=next_action,
                action_reason=action_reason,
                contradiction_notes=contradiction_notes,
                evidence_count=max(len(matched_evidence), previous.evidence_count if previous else 0),
                source_count=source_count,
                source_domains=source_domains or (previous.source_domains if previous else []),
                confidence=confidence,
                gaps=gaps,
                follow_up_queries=list(dict.fromkeys(follow_up_queries)),
                source_strategy=task.source_strategy,
                last_iteration=current_iteration if result else (previous.last_iteration if previous else 0),
            )
        )
    return branch_states


def _select_actionable_tasks(tasks: list[ResearchTask], branch_states: list[ResearchBranchState]) -> list[ResearchTask]:
    branch_by_question = {branch.question: branch for branch in branch_states}
    actionable = [
        task
        for task in tasks
        if branch_by_question.get(task.question) is None
        or branch_by_question[task.question].next_action in {"deepen", "widen", "verify"}
    ]
    return actionable or tasks


@traceable(name="supervisor_agent")
async def run_supervisor(state: AgentState) -> dict:
    logger.info("Supervisor agent started")

    decomposition = _parse_splitter_payload(state)
    if decomposition:
        tasks = decomposition.subquestions
    else:
        query = state.get("user_request", {}).get("query", "")
        tasks = [ResearchTask(id="task-1", question=query, priority=1)]
        decomposition = TaskDecomposition(main_question=query, subquestions=tasks)

    follow_up_queries = list(state.get("data_queries", []) or [])
    tasks = _merge_follow_up_tasks(tasks, follow_up_queries)
    decomposition = decomposition.model_copy(update={"subquestions": tasks})

    tasks = sorted(tasks, key=lambda task: (task.priority, task.id))
    if settings.dev_mode and len(tasks) > MAX_QUERIES_DEV:
        tasks = tasks[:MAX_QUERIES_DEV]
        logger.info(f"[DEV] Capped supervisor tasks to {MAX_QUERIES_DEV}")

    tasks = await _attach_source_strategy(tasks)
    branch_states = _build_branch_states(state, tasks)
    actionable_tasks = _select_actionable_tasks(tasks, branch_states)

    if len(actionable_tasks) <= 1:
        batches = ParallelBatches(
            batches=[QueryBatch(queries=[actionable_tasks[0].question], mode="parallel", rationale="Single task")],
            total_queries=len(actionable_tasks),
            strategy_rationale="Single task, no orchestration needed",
        )
        cost = 0.0
    else:
        model = get_model(AgentTask.SUPERVISION)
        task_payload = [
            {
                "id": task.id,
                "question": task.question,
                "depends_on": task.depends_on,
                "priority": task.priority,
                "source_strategy": task.source_strategy,
            }
            for task in actionable_tasks
        ]
        raw = await _plan_batches(task_payload, model)
        raw_text = raw if isinstance(raw, str) else ""
        if not raw_text.strip():
            logger.warning("Supervisor planner returned empty content, using dependency-aware fallback")
            batches = _fallback_batches(actionable_tasks)
        else:
            try:
                parsed = parse_llm_json(raw_text, context="supervisor")
                batches = ParallelBatches(**parsed)
            except Exception as exc:
                logger.warning(f"Supervisor parse failed, using dependency-aware fallback: {exc}")
                batches = _fallback_batches(actionable_tasks)
        cost = estimate_cost(AgentTask.SUPERVISION, len(json.dumps(task_payload)) // 4, len(raw_text) // 4)

    data_queries = [task.question for task in actionable_tasks]
    iteration = state.get("iteration", 0) + 1
    logger.info(
        f"Supervisor orchestrated {len(actionable_tasks)} actionable tasks into {len(batches.batches)} batches "
        f"(iteration {iteration})"
    )

    return {
        "task_decomposition": decomposition,
        "research_tasks": tasks,
        "branch_states": branch_states,
        "data_queries": data_queries,
        "parallel_batches": batches,
        "hypotheses": decomposition.hypotheses,
        "unresolved_questions": decomposition.ambiguities,
        "revision_count": state.get("revision_count", 0),
        "current_agent": "supervisor",
        "status": "researching",
        "iteration": iteration,
        "max_iterations": state.get("max_iterations", 3),
        "cost_usd": state.get("cost_usd", 0.0) + cost,
    }
