"""Contrarian Pass — critiques an Analyst block without rewriting it.

Runs AFTER the Analyst, BEFORE Bisociator / Summarizer. Consumes a Block, returns
the same Block enriched with:
    - `contrarian_critique`: 3–8 one-line weaknesses tied to specific claims/numbers
    - `strongest_point`: one sentence naming the hardest-to-refute claim in the block

Failure mode: on LLM error or schema mismatch we return the block unchanged. Never
raises — the Analyst output must survive even if the critic is flaky.
"""
from __future__ import annotations

import json
import logging

from pydantic import BaseModel, Field

from config import load_prompt, model_for
from llm import call_json
from models import Block

log = logging.getLogger("contrarian")

_SYSTEM = load_prompt("contrarian_critic")


class _CriticPayload(BaseModel):
    contrarian_critique: list[str] = Field(default_factory=list)
    strongest_point: str | None = None


def _block_brief(block: Block) -> str:
    """Compact JSON of the block — enough for the critic, trimmed to fit context."""
    return json.dumps(
        {
            "cell": block.cell,
            "summary": block.summary,
            "findings": [
                {
                    "claim": f.claim,
                    "source": f.source,
                    "source_label": f.source_label,
                    "source_type": f.source_type,
                    "numeric_values": f.numeric_values,
                    "critique": f.critique,
                    "adjusted_range": f.adjusted_range,
                    "bias_type": f.bias_type,
                }
                for f in block.findings
            ],
            "assumptions": block.assumptions,
            "quant_metrics": [m.model_dump() for m in block.quant_metrics],
            "gaps": block.gaps,
        },
        ensure_ascii=False,
        indent=2,
    )


async def critique_block(block: Block, *, model: str | None = None) -> Block:
    """Return `block` with contrarian_critique + strongest_point populated."""
    if not block.summary and not block.findings:
        return block
    user = (
        f"Блок от Analyst'а для ячейки «{block.cell}»:\n\n"
        f"{_block_brief(block)}\n\n"
        "Приложи contrarian_critique и strongest_point по контракту из system prompt. Только JSON."
    )
    try:
        payload = await call_json(
            model=model or model_for("analyst"),
            system=_SYSTEM,
            user=user,
            schema=_CriticPayload,
            temperature=0.4,
            max_tokens=4000,
        )
    except Exception as exc:
        log.warning("contrarian [%s] failed: %s", block.cell, exc)
        return block

    return block.model_copy(update={
        "contrarian_critique": payload.contrarian_critique or [],
        "strongest_point": payload.strongest_point,
    })
