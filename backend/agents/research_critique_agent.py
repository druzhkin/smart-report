from __future__ import annotations

import json
import re
from statistics import mean

import httpx
from langsmith import traceable
from loguru import logger

from backend.config import settings
from backend.pipeline.model_router import AgentTask, estimate_cost, get_model
from backend.pipeline.state import AgentState
from backend.schemas.quality import CritiqueScore, ResearchCritiqueResult
from backend.utils.json_parse import parse_llm_json, supports_json_mode
from backend.utils.retry import llm_retry


@llm_retry()
async def _call_llm(system_prompt: str, user_message: str, model: str) -> str:
    async with httpx.AsyncClient(timeout=180) as client:
        resp = await client.post(
            f"{settings.openrouter_base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.openrouter_api_key}",
                "HTTP-Referer": "https://smart-report.app",
                "X-Title": "Smart Report",
            },
            json={
                "model": model,
                "provider": {"order": ["OpenAI"]},
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                "temperature": 1,
                **( {"response_format": {"type": "json_object"}} if supports_json_mode(model) else {} ),
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


def _dedupe_keep_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        output.append(normalized)
    return output


def _topic_signature(text: str) -> tuple[str, ...]:
    tokens = [
        token
        for token in re.findall(r"[a-zA-Zа-яА-Я0-9]+", (text or "").lower())
        if len(token) > 3 and not token.isdigit()
    ]
    return tuple(sorted(dict.fromkeys(tokens[:6])))


def _extract_numbers(text: str) -> list[float]:
    values: list[float] = []
    for match in re.findall(r"\d+(?:[.,]\d+)?", text or ""):
        try:
            values.append(float(match.replace(",", ".")))
        except ValueError:
            continue
    return values


def _detect_contradictions(state: AgentState) -> list[dict]:
    evidence_items = list(state.get("evidence_items", []) or [])
    grouped: dict[tuple[str, ...], list[dict]] = {}

    for item in evidence_items:
        payload = item.model_dump(mode="json") if hasattr(item, "model_dump") else dict(item)
        signature = _topic_signature(payload.get("claim", ""))
        if not signature:
            continue
        grouped.setdefault(signature, []).append(payload)

    contradictions: list[dict] = []
    for signature, items in grouped.items():
        if len(items) < 2:
            continue
        numbers = [number for item in items for number in _extract_numbers(item.get("claim", ""))]
        has_direction_conflict = (
            any(word in item.get("claim", "").lower() for item in items for word in ["grow", "increase", "up", "рост"])
            and any(word in item.get("claim", "").lower() for item in items for word in ["decline", "decrease", "down", "снижен", "паден"])
        )
        numeric_spread = max(numbers) - min(numbers) if len(numbers) >= 2 else 0.0
        if has_direction_conflict or numeric_spread > 25:
            contradictions.append(
                {
                    "topic": " ".join(signature[:4]),
                    "evidence_ids": [item["id"] for item in items[:4]],
                    "claims": [item.get("claim", "") for item in items[:4]],
                    "reason": (
                        "directional conflict detected"
                        if has_direction_conflict
                        else f"numeric spread detected ({numeric_spread:.1f})"
                    ),
                }
            )
    return contradictions


def _heuristic_critique(state: AgentState) -> ResearchCritiqueResult:
    results = list(state.get("research_results", []) or [])
    tasks = list(state.get("research_tasks", []) or [])
    raw_evidence_items = list(state.get("evidence_items", []) or [])
    evidence_items = [
        item.model_dump(mode="json") if hasattr(item, "model_dump") else dict(item)
        for item in raw_evidence_items
    ]
    reflect_result = state.get("reflect_result")
    citation = state.get("citation_verification")
    contradictions = _detect_contradictions(state)

    total_tasks = len(tasks) or 1
    covered_queries = {result.query for result in results}
    covered_tasks = sum(1 for task in tasks if task.question in covered_queries) if tasks else len(results)
    coverage_ratio = covered_tasks / total_tasks if total_tasks else 1.0

    source_counts = [len(result.sources) for result in results]
    avg_sources = mean(source_counts) if source_counts else 0.0
    total_sources = sum(source_counts)
    unique_domains = {
        source.domain
        for result in results
        for source in result.sources
        if source.domain
    }
    source_score = min(
        1.0,
        0.4
        + min(0.25, avg_sources * 0.12)
        + min(0.2, len(unique_domains) * 0.05)
        + (0.15 if citation and citation.passed else 0.0),
    )

    factual_score = 0.85 if citation and citation.passed else 0.55
    if citation and citation.fabricated_count:
        factual_score = max(0.2, factual_score - citation.fabricated_count * 0.2)

    depth_score = min(1.0, 0.35 + len(evidence_items) * 0.03 + len(results) * 0.06)
    logic_score = 0.8
    if reflect_result and reflect_result.issues:
        major_issues = sum(1 for issue in reflect_result.issues if issue.severity in {"critical", "major"})
        logic_score = max(0.35, 0.85 - major_issues * 0.12)

    scores = CritiqueScore(
        factual_accuracy=max(0.0, min(1.0, factual_score)),
        coverage=max(0.0, min(1.0, coverage_ratio)),
        logic=max(0.0, min(1.0, logic_score)),
        depth=max(0.0, min(1.0, depth_score)),
        sources=max(0.0, min(1.0, source_score)),
    )
    overall = mean([
        scores.factual_accuracy,
        scores.coverage,
        scores.logic,
        scores.depth,
        scores.sources,
    ])

    blocking_issues: list[str] = []
    recommendations: list[str] = []
    challenged_claims: list[dict] = []
    follow_up_queries: list[str] = []

    if results and total_sources == 0:
        blocking_issues.append("Research returned no usable citations or sources.")
        recommendations.append("Stop orchestration and repair the research provider or citation extraction before another loop.")

    if citation and not citation.passed:
        blocking_issues.append("Citation verification failed to meet the pass threshold.")
        follow_up_queries.append("Re-run the weakest claims against independent verified sources.")
    if coverage_ratio < 0.75:
        blocking_issues.append("Too many planned research tasks remain uncovered.")
    if avg_sources < 2 and results and total_sources > 0:
        blocking_issues.append("Research branches do not have enough independent sources.")
        follow_up_queries.extend(
            f"Find two additional independent sources for: {result.query}"
            for result in results[:4]
            if len(result.sources) < 2
        )
    if reflect_result:
        recommendations.extend(reflect_result.weaknesses)
        recommendations.extend(reflect_result.gaps)
        follow_up_queries.extend(reflect_result.additional_queries)
        for issue in reflect_result.issues:
            if issue.severity == "critical":
                blocking_issues.append(issue.description)

    if contradictions:
        blocking_issues.append("Contradictory evidence was detected across research branches.")
        recommendations.append("Run contradiction verification on conflicting branches before synthesis.")
        for contradiction in contradictions[:4]:
            follow_up_queries.append(
                f"Verify contradiction for {contradiction['topic']}: reconcile these competing claims with authoritative sources."
            )
            challenged_claims.append(
                {
                    "claim": contradiction["claims"][0],
                    "challenge": contradiction["reason"],
                    "severity": "high",
                }
            )

    for evidence in evidence_items:
        if float(evidence.get("confidence", 0.0)) < 0.55:
            challenged_claims.append(
                {
                    "claim": evidence.get("claim", ""),
                    "challenge": "Confidence is too low for synthesis without stronger corroboration.",
                    "severity": "medium",
                }
            )

    verdict = "ACCEPT" if overall >= 0.72 and not blocking_issues else "REVISE"
    if verdict == "REVISE":
        recommendations.append("Run another research cycle focused on gaps and low-confidence branches.")

    return ResearchCritiqueResult(
        verdict=verdict,
        scores=scores,
        overall_score=max(0.0, min(1.0, overall)),
        blocking_issues=_dedupe_keep_order(blocking_issues),
        recommendations=_dedupe_keep_order(recommendations),
        challenged_claims=challenged_claims[:8],
        follow_up_queries=_dedupe_keep_order(follow_up_queries),
    )


def _merge_critique(heuristic: ResearchCritiqueResult, parsed: ResearchCritiqueResult) -> ResearchCritiqueResult:
    zero_source_mode = any(
        "no usable citations" in issue.lower() or "no usable sources" in issue.lower()
        for issue in heuristic.blocking_issues
    )
    parsed_follow_up_queries = parsed.follow_up_queries
    if zero_source_mode:
        parsed_follow_up_queries = [
            query for query in parsed.follow_up_queries
            if not query.startswith("Find two additional independent sources for:")
        ]

    merged_score = CritiqueScore(
        factual_accuracy=min(heuristic.scores.factual_accuracy, parsed.scores.factual_accuracy),
        coverage=min(heuristic.scores.coverage, parsed.scores.coverage),
        logic=min(heuristic.scores.logic, parsed.scores.logic),
        depth=min(heuristic.scores.depth, parsed.scores.depth),
        sources=min(heuristic.scores.sources, parsed.scores.sources),
    )
    merged_blockers = _dedupe_keep_order(heuristic.blocking_issues + parsed.blocking_issues)
    overall = min(heuristic.overall_score, parsed.overall_score)
    verdict = "REVISE" if merged_blockers or heuristic.verdict == "REVISE" or parsed.verdict == "REVISE" else "ACCEPT"
    return ResearchCritiqueResult(
        verdict=verdict,
        scores=merged_score,
        overall_score=overall,
        blocking_issues=merged_blockers,
        recommendations=_dedupe_keep_order(heuristic.recommendations + parsed.recommendations),
        challenged_claims=heuristic.challenged_claims + [
            claim for claim in parsed.challenged_claims if claim not in heuristic.challenged_claims
        ],
        follow_up_queries=_dedupe_keep_order(heuristic.follow_up_queries + parsed_follow_up_queries),
    )


@traceable(name="research_critique_agent")
async def run_research_critique(state: AgentState) -> dict:
    logger.info("Research Critique agent started")
    model = get_model(AgentTask.CRITIQUE)
    results = state.get("research_results", [])
    heuristic = _heuristic_critique(state)

    if not results:
        return {
            "messages": state.get("messages", []) + [
                {"role": "research_critique", "content": heuristic.model_dump_json()}
            ],
            "research_critique_result": heuristic,
            "data_queries": _dedupe_keep_order(list(state.get("data_queries", []) or []) + heuristic.follow_up_queries),
            "current_agent": "research_critique",
        }

    system_prompt = _load_prompt("prompts/research_critique_system.txt")

    citation_msg = next(
        (m for m in state.get("messages", []) if m["role"] == "citation_verifier"),
        None,
    )
    reflect_msg = next(
        (m for m in state.get("messages", []) if m["role"] == "reflect"),
        None,
    )

    context = {
        "research_findings": [r.model_dump(mode="json") for r in results],
        "citation_verification": json.loads(citation_msg["content"]) if citation_msg else None,
        "reflection": json.loads(reflect_msg["content"]) if reflect_msg else None,
    }
    user_message = json.dumps(context, default=str)

    raw = await _call_llm(system_prompt, user_message, model)
    try:
        data = parse_llm_json(raw, context="research_critique")
        critique = _merge_critique(heuristic, ResearchCritiqueResult(**data))
    except (ValueError, Exception) as exc:
        logger.warning(f"Research critique parse failed, using heuristic fallback: {exc}")
        critique = heuristic

    cost = estimate_cost(
        AgentTask.CRITIQUE, len(user_message) // 4, len(raw) // 4
    )

    logger.info(
        f"Research Critique: verdict={critique.verdict}, "
        f"overall={critique.overall_score:.2f}, "
        f"blocking_issues={len(critique.blocking_issues)}"
    )

    return {
        "messages": state.get("messages", []) + [
            {"role": "research_critique", "content": critique.model_dump_json()}
        ],
        "research_critique_result": critique,
        "contradiction_log": _detect_contradictions(state),
        "data_queries": _dedupe_keep_order(list(state.get("data_queries", []) or []) + critique.follow_up_queries),
        "cost_usd": state.get("cost_usd", 0) + cost,
        "current_agent": "research_critique",
    }


def _load_prompt(path: str) -> str:
    try:
        with open(path) as f:
            return f.read()
    except FileNotFoundError:
        logger.warning(f"Prompt file not found: {path}, using fallback")
        return _FALLBACK_PROMPT


_FALLBACK_PROMPT = """\
You are a deep research critique agent (o3). Your role is rigorous fact-checking.

Evaluate research on exactly 5 criteria (score 0.0-1.0 each):
1. factual_accuracy — Are claims factually correct and verifiable?
2. coverage — Does the research cover the topic comprehensively?
3. logic — Is the reasoning logically sound, free of fallacies?
4. depth — Is the analysis deep enough for the stated complexity?
5. sources — Are sources reliable, diverse, and properly cited?

Determine verdict:
- ACCEPT: overall_score >= 0.7 AND no blocking issues
- REVISE: overall_score < 0.7 OR blocking issues exist

Return JSON:
{
    "verdict": "ACCEPT" or "REVISE",
    "scores": {
        "factual_accuracy": 0.0-1.0,
        "coverage": 0.0-1.0,
        "logic": 0.0-1.0,
        "depth": 0.0-1.0,
        "sources": 0.0-1.0
    },
    "overall_score": 0.0-1.0,
    "blocking_issues": ["issue that MUST be fixed before acceptance"],
    "recommendations": ["optional improvement"],
    "challenged_claims": [{"claim": "...", "challenge": "...", "severity": "high|medium|low"}]
}
"""
