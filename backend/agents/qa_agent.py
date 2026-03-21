from __future__ import annotations

import asyncio
import base64
import json
import os

import httpx
from langsmith import traceable
from loguru import logger

from backend.config import settings
from backend.pipeline.model_router import AgentTask, estimate_cost, get_model
from backend.pipeline.state import AgentState
from backend.schemas.qa_result import (
    SUBSTANCE_RUBRIC,
    VISUAL_RUBRIC,
    QAIssue,
    QAResult,
    QAVerdict,
)
from backend.utils.json_parse import parse_llm_json, supports_json_mode
from backend.utils.push import send_push_notification
from backend.utils.retry import llm_retry


def _load_prompt(path: str) -> str:
    try:
        with open(path) as f:
            return f.read()
    except FileNotFoundError:
        defaults = {
            "prompts/qa_visual_system.txt": (
                "You are a visual quality reviewer. Check report formatting, "
                "readability, structure. Return JSON with 'score' (0-1) and 'issues' array."
            ),
            "prompts/qa_substance_system.txt": (
                "You are a substance quality reviewer. Check factual accuracy, "
                "logical coherence, citation quality. Return JSON with 'score' (0-1), "
                "'citation_score' (0-1), and 'issues' array."
            ),
        }
        return defaults.get(path, "You are a QA reviewer. Return JSON with score and issues.")


def _encode_image(path: str) -> str | None:
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


@llm_retry()
async def _call_visual_qa(
    system: str, report_json: str, chart_paths: list[str], model: str
) -> str:
    """Visual QA with claude-opus-4.6 vision — sends chart PNGs as images."""
    messages: list[dict] = [{"role": "system", "content": system}]

    user_content: list[dict] = [{"type": "text", "text": report_json}]

    for cp in chart_paths:
        b64 = _encode_image(cp)
        if b64:
            user_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64}"},
            })

    messages.append({"role": "user", "content": user_content})

    payload: dict = {
        "model": model,
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": 8192,
    }
    if supports_json_mode(model):
        payload["response_format"] = {"type": "json_object"}
    async with httpx.AsyncClient(timeout=180) as client:
        resp = await client.post(
            f"{settings.openrouter_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


@llm_retry()
async def _call_substance_qa(system: str, report_json: str, model: str) -> str:
    """Substance QA with o3 — text-only deep reasoning."""
    payload: dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": report_json},
        ],
        "temperature": 0.1,
        "max_tokens": 8192,
    }
    if supports_json_mode(model):
        payload["response_format"] = {"type": "json_object"}
    async with httpx.AsyncClient(timeout=180) as client:
        resp = await client.post(
            f"{settings.openrouter_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


def _determine_verdict(
    visual_score: float,
    substance_score: float,
    issues: list[QAIssue],
) -> QAVerdict:
    has_critical = any(i.severity == "critical" for i in issues)
    overall = (visual_score + substance_score) / 2

    if has_critical or overall < 0.4:
        return QAVerdict.REJECT
    if overall >= 0.7 and not has_critical:
        return QAVerdict.PASS
    return QAVerdict.REVISE


def _prioritize_issues(issues: list[QAIssue]) -> list[QAIssue]:
    severity_order = {"critical": 0, "major": 1, "minor": 2}
    return sorted(issues, key=lambda i: (severity_order.get(i.severity, 3), i.priority))


def _build_revision_instructions(issues: list[QAIssue], verdict: QAVerdict) -> list[str]:
    if verdict == QAVerdict.PASS:
        return []
    instructions: list[str] = []
    for issue in _prioritize_issues(issues):
        if issue.severity in ("critical", "major"):
            instructions.append(f"[{issue.severity.upper()}] {issue.location}: {issue.suggestion}")
    return instructions


@traceable(name="qa_agent")
async def run_qa(state: AgentState) -> dict:
    logger.info("QA agent started")
    report = state.get("report")
    if not report:
        logger.warning("No report to QA")
        return {
            "qa_result": QAResult(verdict=QAVerdict.REJECT, overall_score=0.0),
            "current_agent": "qa",
        }

    visual_model = get_model(AgentTask.QA_VISUAL)
    substance_model = get_model(AgentTask.QA_SUBSTANCE)

    system_visual = _load_prompt("prompts/qa_visual_system.txt")
    system_substance = _load_prompt("prompts/qa_substance_system.txt")

    system_visual += f"\n\nRubric:\n{json.dumps(VISUAL_RUBRIC)}"
    system_substance += f"\n\nRubric:\n{json.dumps(SUBSTANCE_RUBRIC)}"

    report_json = json.dumps(report.model_dump(mode="json"), default=str)
    chart_paths = state.get("chart_paths", [])

    raw_visual, raw_substance = await asyncio.gather(
        _call_visual_qa(system_visual, report_json, chart_paths, visual_model),
        _call_substance_qa(system_substance, report_json, substance_model),
    )

    try:
        visual = parse_llm_json(raw_visual, context="qa_visual")
    except ValueError:
        logger.warning("QA visual parse failed, using defaults")
        visual = {"score": 0.5, "issues": []}

    try:
        substance = parse_llm_json(raw_substance, context="qa_substance")
    except ValueError:
        logger.warning("QA substance parse failed, using defaults")
        substance = {"score": 0.5, "citation_score": 0.5, "issues": []}

    issues: list[QAIssue] = []
    for idx, issue_data in enumerate(visual.get("issues", []) + substance.get("issues", [])):
        # Normalise common LLM field-name variants so validation succeeds.
        if "issue" in issue_data and "category" not in issue_data:
            issue_data["category"] = issue_data.pop("issue")
        if "area" in issue_data and "location" not in issue_data:
            issue_data["location"] = issue_data.pop("area")
        if "recommendation" in issue_data and "suggestion" not in issue_data:
            issue_data["suggestion"] = issue_data.pop("recommendation")
        issue_data.setdefault("category", "general")
        issue_data.setdefault("severity", "minor")
        issue_data.setdefault("location", "general")
        issue_data.setdefault("description", str(issue_data))
        issue_data.setdefault("suggestion", issue_data.get("description", "Review and improve"))
        issue_data.setdefault("priority", idx)
        try:
            issues.append(QAIssue(**issue_data))
        except Exception as exc:
            logger.warning(f"Skipping malformed QA issue #{idx}: {exc}")

    visual_score = visual.get("score", 0.5)
    substance_score = substance.get("score", 0.5)
    citation_score = substance.get("citation_score", 0.5)
    overall = (visual_score + substance_score) / 2

    issues = _prioritize_issues(issues)
    verdict = _determine_verdict(visual_score, substance_score, issues)
    revision_instructions = _build_revision_instructions(issues, verdict)

    qa_result = QAResult(
        verdict=verdict,
        passed=verdict == QAVerdict.PASS,
        overall_score=overall,
        issues=issues,
        substance_score=substance_score,
        visual_score=visual_score,
        citation_score=citation_score,
        revision_instructions=revision_instructions,
    )

    visual_cost = estimate_cost(AgentTask.QA_VISUAL, len(report_json) // 4, len(raw_visual) // 4)
    substance_cost = estimate_cost(
        AgentTask.QA_SUBSTANCE, len(report_json) // 4, len(raw_substance) // 4
    )

    logger.info(
        f"QA result: verdict={verdict.value}, score={overall:.2f}, "
        f"issues={len(issues)}, instructions={len(revision_instructions)}"
    )

    if verdict == QAVerdict.PASS and state.get("session_id"):
        await send_push_notification(state["session_id"], report.title)

    return {
        "qa_result": qa_result,
        "cost_usd": state.get("cost_usd", 0) + visual_cost + substance_cost,
        "current_agent": "qa",
        "status": "qa",
    }
