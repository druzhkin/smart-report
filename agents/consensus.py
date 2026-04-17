"""Consensus Layer — meta-analysis across multiple DR backends' synth reports.

Runs only for premium tier when ≥2 backends returned synthesized reports. Does NOT
re-read primary sources — operates purely over the per-backend narratives, since
agreement on a claim across independent multi-agent researchers is itself the signal.

Failure mode: returns None on LLM error or insufficient input (fewer than 2 synth
reports). Never raises — Report still stands without a consensus_layer field.
"""
from __future__ import annotations

import logging

from config import load_prompt, model_for
from corpus_fetch import Corpus
from llm import call_json
from models import ConsensusLayer

log = logging.getLogger("consensus")

_SYSTEM = load_prompt("consensus")


def _render_reports(corpus: Corpus, cap_per_backend: int = 12000) -> str:
    parts: list[str] = []
    for backend, synth in corpus.synth_reports.items():
        if not synth:
            continue
        body = synth.strip()
        if len(body) > cap_per_backend:
            body = body[:cap_per_backend] + "…"
        parts.append(f"## Отчёт бэкенда `{backend}`\n\n{body}")
    return "\n\n---\n\n".join(parts)


async def build_consensus(goal: str, corpus: Corpus) -> ConsensusLayer | None:
    """Return a ConsensusLayer if ≥2 synth reports exist; otherwise None."""
    reports = {b: s for b, s in (corpus.synth_reports or {}).items() if s}
    if len(reports) < 2:
        log.info("consensus: only %d synth reports — skip (need ≥2)", len(reports))
        return None

    rendered = _render_reports(corpus)
    user = (
        f"Исходный вопрос: {goal}\n\n"
        f"Ниже — {len(reports)} отчётов от независимых deep-research бэкендов "
        f"({', '.join(reports.keys())}). Каждый провёл собственное многошаговое исследование.\n\n"
        f"{rendered}\n\n"
        "Сделай мета-анализ по контракту из system prompt. Только JSON."
    )
    try:
        layer = await call_json(
            model=model_for("analyst"),
            system=_SYSTEM,
            user=user,
            schema=ConsensusLayer,
            temperature=0.25,
            max_tokens=10000,
        )
    except Exception as exc:
        log.warning("consensus: build failed: %s", exc)
        return None

    # Force backends_consulted to reflect reality — model sometimes hallucinates.
    layer.backends_consulted = list(reports.keys())
    log.info(
        "consensus: agreements=%d disagreements=%d confidence=%s",
        len(layer.agreements), len(layer.disagreements), layer.overall_confidence,
    )
    return layer
