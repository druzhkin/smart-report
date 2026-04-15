"""Pre-mortem — Report → list[PreMortem]."""
from __future__ import annotations

import json

from config import load_prompt, model_for
from llm import call_json
from models import Block, Connection, PreMortem
from pydantic import BaseModel

SYSTEM = load_prompt("pre_mortem")


class _PreMortemPayload(BaseModel):
    pre_mortems: list[PreMortem]


async def pre_mortem(
    goal: str,
    blocks: list[Block],
    connections: list[Connection],
) -> list[PreMortem]:
    blocks_compact = [
        {
            "cell": b.cell,
            "summary_excerpt": (b.summary or "")[:1200],
            "strong_findings": [
                {
                    "claim": f.claim,
                    "source_label": f.source_label,
                    "source_type": f.source_type,
                    "bias_type": f.bias_type,
                    "adjusted_range": f.adjusted_range,
                }
                for f in b.findings
                if f.has_numbers
            ][:4],
            "assumptions": b.assumptions,
            "gaps": b.gaps,
        }
        for b in blocks
    ]
    connections_compact = [
        {"domains": c.domains, "nature": c.nature, "description": c.description}
        for c in connections
    ]
    user = (
        f"Цель исследования: {goal}\n\n"
        f"Блоки:\n{json.dumps(blocks_compact, ensure_ascii=False, indent=2)}\n\n"
        f"Связи:\n{json.dumps(connections_compact, ensure_ascii=False, indent=2)}\n\n"
        "Сделай pre-mortem по контракту. Только JSON."
    )
    payload = await call_json(
        model=model_for("analyst"),
        system=SYSTEM,
        user=user,
        schema=_PreMortemPayload,
        temperature=0.4,
    )
    return payload.pre_mortems
