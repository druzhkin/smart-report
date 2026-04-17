"""Analyst: (Cell, list[Finding]) -> Block."""

from __future__ import annotations

import json
from pathlib import Path

from .io import load_prompt
from .llm import chat
from .models import Block, Cell, Finding


async def analyze(
    cell: Cell,
    findings: list[Finding],
    *,
    mock: bool = False,
    log_dir: Path | None = None,
) -> Block:
    system = load_prompt("analyst") or (
        "You are the Analyst. Given a cell and its findings, synthesize a Block "
        "with fields: conclusion, strongest_number, gap, key_assumptions, entities, variables."
    )
    findings_serialized = [f.model_dump() for f in findings]
    user = (
        f"[cell_id={cell.id}] domain={cell.domain} layer={cell.layer}\n"
        f"Findings (JSON):\n{json.dumps(findings_serialized, ensure_ascii=False, indent=2)}\n\n"
        "Return strict JSON with keys: conclusion, strongest_number, gap, "
        "key_assumptions (list[str]), entities (list[str]), variables (list[str])."
    )
    raw = await chat(
        role="analyst",
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        mock=mock,
        log_dir=log_dir,
        response_format={"type": "json_object"} if not mock else None,
    )
    data = json.loads(raw)
    return Block(
        cell_id=cell.id,
        conclusion=data.get("conclusion", ""),
        strongest_number=data.get("strongest_number"),
        gap=data.get("gap"),
        key_assumptions=list(data.get("key_assumptions", [])),
        entities=list(data.get("entities", [])),
        variables=list(data.get("variables", [])),
        findings=findings,
    )
