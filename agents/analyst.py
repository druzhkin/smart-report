"""Analyst — findings of one cell → Block."""
from __future__ import annotations

import json

from config import load_prompt, model_for, settings
from llm import call_json
from models import Block, Finding, ScoutResult
from pydantic import BaseModel

SYSTEM = load_prompt("analyst")


class _AnalystPayload(BaseModel):
    summary: str
    findings: list[Finding]
    gaps: list[str]
    key_entities: list[str]
    assumptions: list[str]


async def analyst(cell: str, scout_results: list[ScoutResult]) -> Block:
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
    user = (
        f"Ячейка матрицы: {cell}\n\n"
        "Материал от Scout'ов (несколько пачек по разным заданиям):\n"
        f"{findings_blob}\n\n"
        "Собери проработанный блок по контракту из system prompt. Только JSON."
    )
    payload = await call_json(
        model=model_for("analyst"),
        system=SYSTEM,
        user=user,
        schema=_AnalystPayload,
        temperature=0.35,
    )
    return Block(
        cell=cell,
        summary=payload.summary,
        findings=payload.findings,
        gaps=payload.gaps,
        key_entities=payload.key_entities,
        assumptions=payload.assumptions,
    )
