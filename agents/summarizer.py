"""Summarizer — Report → ExecutiveSummary + BlockHeaders."""
from __future__ import annotations

import json

from config import load_prompt, model_for, settings
from llm import call_json
from models import Block, BlockHeader, Connection, ExecutiveSummary, Matrix
from pydantic import BaseModel

SYSTEM = load_prompt("summarizer")


class _SummarizerPayload(BaseModel):
    exec_summary: ExecutiveSummary
    block_headers: list[BlockHeader]


async def summarize(
    goal: str,
    matrix: Matrix,
    blocks: list[Block],
    connections: list[Connection],
) -> _SummarizerPayload:
    matrix_compact = [
        {"domain": d.name, "layers": [l.name for l in d.layers]} for d in matrix.domains
    ]
    blocks_compact = [
        {
            "cell": b.cell,
            "summary_excerpt": b.summary[:2500],
            "n_findings": len(b.findings),
            "strong_findings": [
                {"claim": f.claim, "source": f.source, "type": f.source_type}
                for f in b.findings
                if f.has_numbers and f.source_type.startswith("primary")
            ][:5],
            "gaps": b.gaps,
            "assumptions": b.assumptions,
        }
        for b in blocks
    ]
    connections_compact = [
        {"domains": c.domains, "nature": c.nature, "shared": c.shared_entity, "description": c.description}
        for c in connections
    ]
    user = (
        f"Цель: {goal}\n\n"
        f"Матрица:\n{json.dumps(matrix_compact, ensure_ascii=False, indent=2)}\n\n"
        f"Блоки ({len(blocks)}):\n{json.dumps(blocks_compact, ensure_ascii=False, indent=2)}\n\n"
        f"Связи ({len(connections)}):\n{json.dumps(connections_compact, ensure_ascii=False, indent=2)}\n\n"
        "Собери Executive Summary и шапки блоков по контракту из system prompt. Только JSON."
    )
    return await call_json(
        model=model_for("analyst"),
        system=SYSTEM,
        user=user,
        schema=_SummarizerPayload,
        temperature=0.3,
    )
