from __future__ import annotations

import json

import httpx
from langsmith import traceable
from loguru import logger

from backend.config import settings
from backend.pipeline.model_router import AgentTask, estimate_cost, get_model
from backend.pipeline.state import AgentState
from backend.schemas.quality import ReflectIssue, ReflectResult
from backend.utils.json_parse import parse_llm_json, supports_json_mode
from backend.utils.retry import llm_retry


@llm_retry()
async def _call_llm(system_prompt: str, user_message: str, model: str) -> str:
    payload: dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "temperature": 0.4,
    }
    if supports_json_mode(model):
        payload["response_format"] = {"type": "json_object"}
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{settings.openrouter_base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.openrouter_api_key}",
                "HTTP-Referer": "https://smart-report.app",
                "X-Title": "Smart Report",
            },
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


def _dedupe_keep_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def _heuristic_reflection(state: AgentState) -> ReflectResult:
    results = list(state.get("research_results", []) or [])
    tasks = list(state.get("research_tasks", []) or [])
    evidence_items = list(state.get("evidence_items", []) or [])
    unresolved = list(state.get("unresolved_questions", []) or [])

    issues: list[ReflectIssue] = []
    strengths: list[str] = []
    weaknesses: list[str] = []
    gaps: list[str] = []
    additional_queries: list[str] = []

    query_to_result = {result.query: result for result in results}
    covered_task_ids = {
        task.id
        for task in tasks
        if task.question in query_to_result
    }
    uncovered_tasks = [task for task in tasks if task.id not in covered_task_ids]
    if uncovered_tasks:
        issues.append(
            ReflectIssue(
                description=f"{len(uncovered_tasks)} planned research tasks were not covered by evidence collection.",
                severity="major",
                section="coverage",
            )
        )
        gaps.append("Planned decomposition coverage is incomplete.")
        additional_queries.extend(task.question for task in uncovered_tasks)

    low_source_results = [result for result in results if len(result.sources) < 2]
    if low_source_results:
        issues.append(
            ReflectIssue(
                description=f"{len(low_source_results)} research branches rely on fewer than 2 sources.",
                severity="major",
                section="evidence",
            )
        )
        gaps.append("Several research branches need source diversification.")
        additional_queries.extend(
            f"Find at least two independent sources for: {result.query}"
            for result in low_source_results[:4]
        )

    unique_domains = {
        source.domain
        for result in results
        for source in result.sources
        if source.domain
    }
    if results and len(unique_domains) < min(3, len(results) + 1):
        issues.append(
            ReflectIssue(
                description="Source diversity is too low for a confident synthesis.",
                severity="major",
                section="sources",
            )
        )
        gaps.append("Domain diversity is below the expected threshold.")

    if unresolved:
        issues.append(
            ReflectIssue(
                description=f"{len(unresolved)} unresolved ambiguities still affect research direction.",
                severity="major",
                section="clarification",
            )
        )
        additional_queries.extend(unresolved)
        weaknesses.append("Important clarifications remain unresolved.")

    if evidence_items:
        strengths.append(f"Collected {len(evidence_items)} evidence items across the current research pass.")
    if unique_domains:
        strengths.append(f"Research currently spans {len(unique_domains)} unique source domains.")
    if not results:
        weaknesses.append("No research findings available yet.")
    if not evidence_items:
        weaknesses.append("Evidence graph is still empty.")
        gaps.append("No structured evidence items are available for synthesis.")

    penalty = 0.0
    penalty += min(0.45, len(uncovered_tasks) * 0.12)
    penalty += min(0.3, len(low_source_results) * 0.08)
    penalty += 0.1 if unresolved else 0.0
    penalty += 0.15 if results and len(unique_domains) < 2 else 0.0
    quality_score = max(0.15, min(0.95, 0.9 - penalty))

    return ReflectResult(
        issues=issues,
        additional_queries=_dedupe_keep_order(additional_queries),
        strengths=_dedupe_keep_order(strengths),
        weaknesses=_dedupe_keep_order(weaknesses),
        gaps=_dedupe_keep_order(gaps),
        quality_score=quality_score,
        needs_more_research=bool(issues),
    )


def _merge_reflection(heuristic: ReflectResult, parsed: ReflectResult) -> ReflectResult:
    merged_issues = heuristic.issues + [
        issue
        for issue in parsed.issues
        if (issue.description, issue.section) not in {(i.description, i.section) for i in heuristic.issues}
    ]
    return ReflectResult(
        issues=merged_issues,
        additional_queries=_dedupe_keep_order(heuristic.additional_queries + parsed.additional_queries),
        strengths=_dedupe_keep_order(heuristic.strengths + parsed.strengths),
        weaknesses=_dedupe_keep_order(heuristic.weaknesses + parsed.weaknesses),
        gaps=_dedupe_keep_order(heuristic.gaps + parsed.gaps),
        quality_score=min(heuristic.quality_score, parsed.quality_score),
        needs_more_research=heuristic.needs_more_research or parsed.needs_more_research,
    )


@traceable(name="reflect_agent")
async def run_reflect(state: AgentState) -> dict:
    logger.info("Reflect agent started")
    model = get_model(AgentTask.REFLECTION)
    results = state.get("research_results", [])
    heuristic = _heuristic_reflection(state)

    if not results:
        return {
            "messages": state.get("messages", []) + [
                {"role": "reflect", "content": heuristic.model_dump_json()}
            ],
            "reflect_result": heuristic,
            "data_queries": _dedupe_keep_order(list(state.get("data_queries", []) or []) + heuristic.additional_queries),
            "current_agent": "reflect",
        }

    system_prompt = _load_prompt("prompts/reflect_system.txt")

    intake = state.get("intake_result")
    context = {
        "original_query": intake.cleaned_query if intake else state.get("original_request", ""),
        "research_findings": [r.model_dump(mode="json") for r in results],
    }
    user_message = json.dumps(context, default=str)

    raw = await _call_llm(system_prompt, user_message, model)

    try:
        data = parse_llm_json(raw, context="reflect_agent")
        reflect_result = _merge_reflection(heuristic, ReflectResult(**data))
    except (ValueError, Exception) as exc:
        logger.warning(f"Reflect parse failed, using heuristic fallback: {exc}")
        reflect_result = heuristic

    cost = estimate_cost(
        AgentTask.REFLECTION, len(user_message) // 4, len(raw) // 4
    )

    logger.info(
        f"Reflect: {len(reflect_result.issues)} issues, "
        f"{len(reflect_result.additional_queries)} additional queries, "
        f"quality_score={reflect_result.quality_score:.2f}"
    )

    return {
        "messages": state.get("messages", []) + [
            {"role": "reflect", "content": reflect_result.model_dump_json()}
        ],
        "reflect_result": reflect_result,
        "data_queries": _dedupe_keep_order(list(state.get("data_queries", []) or []) + reflect_result.additional_queries),
        "cost_usd": state.get("cost_usd", 0) + cost,
        "current_agent": "reflect",
    }


def _load_prompt(path: str) -> str:
    try:
        with open(path) as f:
            return f.read()
    except FileNotFoundError:
        logger.warning(f"Prompt file not found: {path}, using fallback")
        return _FALLBACK_PROMPT


_FALLBACK_PROMPT = """\
You are a first-pass research quality reflection agent (claude-opus-4.6).

Analyze the research findings critically. Identify:
1. Structure gaps — missing sections, weak transitions
2. Content gaps — topics not covered, shallow treatment
3. Evidence gaps — unsupported claims, single-source conclusions
4. Perspective gaps — missing viewpoints, bias indicators

Return JSON matching this schema:
{
    "issues": [{"description": "...", "severity": "critical|major|minor", "section": "..."}],
    "additional_queries": ["query to fill gap 1", "..."],
    "strengths": ["..."],
    "weaknesses": ["..."],
    "gaps": ["..."],
    "quality_score": 0.0-1.0,
    "needs_more_research": true/false
}
"""
