"""Consistency Critic — post-Synthesizer validation step.

Scans the complete FinalReport for internal contradictions between sections
and returns a structured ConsistencyReport. Designed to run after the
Synthesizer and before final export.

Max 1 retry loop is enforced by the orchestrator (v4_orchestrator.py),
not here. This module is stateless: call validate_consistency() with any
FinalReport and get back a ConsistencyReport.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from .events import EventEmitter, NullEmitter
from .io import extract_json, load_prompt
from .llm import LLMResult, call_json
from .models import FinalReport

CRITIC_MODEL = "anthropic/claude-opus-4-7"


class ConsistencyIssue(BaseModel):
    severity: Literal["critical", "material", "minor"]
    category: Literal[
        "number_conflict",
        "ranking_qa_mismatch",
        "verdict_evidence_gap",
        "table_prose_disagreement",
        "source_attribution_inconsistency",
    ]
    location_a: str  # e.g. "Ключевые цифры — пункт 3"
    statement_a: str
    location_b: str  # e.g. "Ranking — позиция 6"
    statement_b: str
    why_inconsistent: str
    suggested_fix: str


class ConsistencyReport(BaseModel):
    issues: list[ConsistencyIssue]
    severity_summary: dict[str, int]
    overall_verdict: Literal["pass", "needs_revision", "critical_failure"]
    # pass           = 0 critical issues
    # needs_revision = 1-2 critical, or >3 material
    # critical_failure = >2 critical


def _compute_verdict(issues: list[ConsistencyIssue]) -> tuple[Literal["pass", "needs_revision", "critical_failure"], dict[str, int]]:
    """Derive overall_verdict and severity_summary from list of issues."""
    counts: dict[str, int] = {"critical": 0, "material": 0, "minor": 0}
    for issue in issues:
        counts[issue.severity] = counts.get(issue.severity, 0) + 1

    n_critical = counts["critical"]
    n_material = counts["material"]

    if n_critical > 2:
        verdict: Literal["pass", "needs_revision", "critical_failure"] = "critical_failure"
    elif n_critical >= 1 or n_material > 3:
        verdict = "needs_revision"
    else:
        verdict = "pass"

    return verdict, counts


def _build_report_text(report: FinalReport) -> str:
    """Flatten FinalReport into annotated text for the critic to scan."""
    parts: list[str] = []

    parts.append(f"## ВОПРОС\n{report.question}\n")

    # Executive summary
    es = report.executive_summary
    parts.append("## Executive Summary — main_answer")
    parts.append(es.main_answer)

    if es.top_findings:
        parts.append("## Executive Summary — top_findings")
        for i, f in enumerate(es.top_findings, 1):
            parts.append(f"[top_finding_{i}] {f}")

    if es.key_numbers:
        parts.append("## Executive Summary — key_numbers")
        for i, kn in enumerate(es.key_numbers, 1):
            parts.append(f"[key_number_{i}] {kn.value} | {kn.metric} | {kn.subject}")

    # QA section
    if report.qa_section:
        parts.append("## QA Section (прямые ответы на под-вопросы)")
        for i, qa in enumerate(report.qa_section, 1):
            parts.append(f"[qa_{i}_question] {qa.question}")
            parts.append(f"[qa_{i}_answer] {qa.answer}")

    # Ranking
    if report.ranking:
        parts.append("## Ranking (ранжирование)")
        for i, r in enumerate(report.ranking, 1):
            weight_str = f", weight={r.weight}%" if r.weight is not None else ""
            parts.append(f"[ranking_{i}] {r.label}{weight_str} | {r.rationale} | evidence_strength={r.evidence_strength}")

    # Key numbers highlight
    if report.key_numbers_highlight:
        parts.append("## Key Numbers Highlight")
        for i, kn in enumerate(report.key_numbers_highlight, 1):
            parts.append(f"[knh_{i}] {kn.value} | {kn.label} | source_ref={kn.source_ref} | importance={kn.importance}")

    # Tables
    if report.tables:
        parts.append("## Tables")
        for i, t in enumerate(report.tables, 1):
            parts.append(f"[table_{i}_title] {t.title}")
            parts.append(f"[table_{i}_columns] {' | '.join(t.columns)}")
            for j, row in enumerate(t.rows):
                parts.append(f"[table_{i}_row_{j+1}] {' | '.join(row)}")
            if t.caption:
                parts.append(f"[table_{i}_caption] {t.caption}")
            if t.source_ref:
                parts.append(f"[table_{i}_source_ref] {t.source_ref}")

    # Callouts
    if report.callouts:
        parts.append("## Callouts")
        for i, c in enumerate(report.callouts, 1):
            parts.append(f"[callout_{i}] kind={c.kind} | {c.title}: {c.body}")

    # Main synthesis
    if report.main_synthesis:
        parts.append("## Main Synthesis (основной корпус)")
        parts.append(report.main_synthesis)

    # Consensus
    if report.consensus_section:
        parts.append("## Consensus Section")
        parts.append(report.consensus_section)

    # Conflicts
    if report.conflicts_section:
        parts.append("## Conflicts Section")
        parts.append(report.conflicts_section)

    # Gaps filled
    if report.gaps_filled_section:
        parts.append("## Gaps Filled Section")
        parts.append(report.gaps_filled_section)

    # Sources
    if report.all_sources:
        parts.append("## Sources")
        for i, s in enumerate(report.all_sources, 1):
            parts.append(f"[source_{i}] {s.title} | url={s.url} | tool={s.tool} | reliability={s.reliability}")

    return "\n\n".join(parts)


async def validate_consistency(
    report: FinalReport,
    *,
    emitter: EventEmitter | None = None,
    log_dir: Path | None = None,
    mock: bool = False,
    model: str | None = None,
) -> ConsistencyReport:
    """Call Opus to scan the full FinalReport for internal contradictions.

    Returns a ConsistencyReport with all found issues and an overall verdict.
    Mock mode returns an empty (pass) report without calling LLM.
    """
    em: EventEmitter = emitter or NullEmitter()
    em.emit("critic", "Проверяю отчёт на внутренние противоречия", data={})

    if mock:
        return ConsistencyReport(
            issues=[],
            severity_summary={"critical": 0, "material": 0, "minor": 0},
            overall_verdict="pass",
        )

    system = load_prompt("synthesis_critic")
    if not system:
        raise RuntimeError("prompts/synthesis_critic.md not found")

    report_text = _build_report_text(report)
    user = (
        "Ниже — полный текст FinalReport для аудита на внутренние противоречия.\n\n"
        f"{report_text}\n\n"
        "---\n"
        "Верни строгий JSON-объект по схеме из системного промта. "
        "Без markdown-обёртки, без комментариев."
    )

    last_err: Exception | None = None
    for attempt in range(3):
        llm_result: LLMResult = await call_json(
            role="synthesis_critic",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            model=model or CRITIC_MODEL,
            temperature=0.2,
            mock=False,
            log_dir=log_dir,
            response_format={"type": "json_object"},
        )
        try:
            data = extract_json(llm_result.text)
        except (ValueError, json.JSONDecodeError) as err:
            last_err = err
            if attempt < 2:
                continue
            raise
        if not isinstance(data, dict):
            last_err = ValueError(f"Critic returned non-object JSON: {type(data).__name__}")
            if attempt < 2:
                continue
            raise last_err
        break
    else:
        assert last_err is not None
        raise last_err

    issues = _parse_issues(data.get("issues", []))
    verdict, severity_summary = _compute_verdict(issues)

    em.emit(
        "critic",
        "Проверка завершена",
        data={
            "issues_count": len(issues),
            "critical": severity_summary.get("critical", 0),
            "material": severity_summary.get("material", 0),
            "minor": severity_summary.get("minor", 0),
            "verdict": verdict,
        },
    )

    return ConsistencyReport(
        issues=issues,
        severity_summary=severity_summary,
        overall_verdict=verdict,
    )


def _parse_issues(raw_list: object) -> list[ConsistencyIssue]:
    """Coerce LLM output list into typed ConsistencyIssue list, skipping bad entries."""
    if not isinstance(raw_list, list):
        return []

    _valid_severity = ("critical", "material", "minor")
    _valid_category = (
        "number_conflict",
        "ranking_qa_mismatch",
        "verdict_evidence_gap",
        "table_prose_disagreement",
        "source_attribution_inconsistency",
    )

    issues: list[ConsistencyIssue] = []
    for item in raw_list:
        if not isinstance(item, dict):
            continue
        sev = item.get("severity")
        cat = item.get("category")
        if sev not in _valid_severity or cat not in _valid_category:
            continue
        issues.append(
            ConsistencyIssue(
                severity=sev,  # type: ignore[arg-type]
                category=cat,  # type: ignore[arg-type]
                location_a=str(item.get("location_a", "")),
                statement_a=str(item.get("statement_a", "")),
                location_b=str(item.get("location_b", "")),
                statement_b=str(item.get("statement_b", "")),
                why_inconsistent=str(item.get("why_inconsistent", "")),
                suggested_fix=str(item.get("suggested_fix", "")),
            )
        )
    return issues


def build_consistency_feedback_text(consistency: ConsistencyReport) -> str:
    """Format critical issues as a feedback block for Synthesizer retry prompt."""
    critical_issues = [i for i in consistency.issues if i.severity == "critical"]
    if not critical_issues:
        return ""

    lines = [
        "ПРЕДЫДУЩАЯ ВЕРСИЯ ОТЧЁТА ПРОВЕРЕНА КРИТИКОМ. Найдены противоречия:\n"
    ]
    for issue in critical_issues:
        lines.append(
            f"- {issue.location_a}: \"{issue.statement_a}\"\n"
            f"  vs {issue.location_b}: \"{issue.statement_b}\"\n"
            f"  Разрешение: {issue.suggested_fix}"
        )

    lines.append(
        "\nВ этой версии ОБЯЗАТЕЛЬНО разрешить эти противоречия. "
        "Либо явно объясни nuance в тексте, "
        "либо перенеси конфликтующие утверждения в conflicts_section, "
        "либо переформулируй."
    )

    return "\n".join(lines)
