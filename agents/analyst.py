"""Analyst — findings of one cell → Block."""
from __future__ import annotations

import json

from config import load_prompt, model_for, settings
from llm import call_json
from models import Analogy, Block, Finding, IndicatorWarning, QuantMetric, ScoutResult
from pydantic import BaseModel, Field
from validators import stamp_block, strip_unverified_numerics

SYSTEM = load_prompt("analyst")


class _AnalystPayload(BaseModel):
    summary: str
    findings: list[Finding]
    gaps: list[str]
    key_entities: list[str]
    assumptions: list[str]
    analogies: list[Analogy] = Field(default_factory=list)
    indicators: list[IndicatorWarning] = Field(default_factory=list)
    decision_point: str | None = None


async def analyst(
    cell: str,
    scout_results: list[ScoutResult],
    *,
    quant_metrics: list[QuantMetric] | None = None,
) -> Block:
    findings_blob = json.dumps(
        [
            {
                "task": sr.task.query_focus,
                "notes": sr.notes,
                "findings": [f.model_dump() for f in sr.findings],
            }
            for sr in scout_results
        ],
        ensure_ascii=False,
        indent=2,
    )
    quant_block = ""
    if quant_metrics:
        quant_block = (
            "\n\nСтруктурированные метрики, извлечённые Quant Extractor'ом "
            "(используй эти числа в summary дословно, не изобретай свои):\n"
            + json.dumps(
                [m.model_dump() for m in quant_metrics],
                ensure_ascii=False,
                indent=2,
            )
        )
    user = (
        f"Ячейка матрицы: {cell}\n\n"
        "Материал от Scout'ов (несколько пачек по разным заданиям):\n"
        f"{findings_blob}"
        f"{quant_block}\n\n"
        "Собери проработанный блок по контракту из system prompt. Только JSON."
    )
    payload = await call_json(
        model=model_for("analyst"),
        system=SYSTEM,
        user=user,
        schema=_AnalystPayload,
        temperature=0.35,
    )
    block = Block(
        cell=cell,
        summary=payload.summary,
        findings=payload.findings,
        gaps=payload.gaps,
        key_entities=payload.key_entities,
        assumptions=payload.assumptions,
        analogies=payload.analogies,
        indicators=payload.indicators,
        decision_point=payload.decision_point,
    )
    # Сначала убираем изобретённые числа из текста, затем stamp_block логирует итог.
    block = strip_unverified_numerics(block)
    return stamp_block(block)
