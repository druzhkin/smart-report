"""Quant Extractor — per-cell LLM pass that pulls structured numeric metrics.

Runs BEFORE the Analyst so the Analyst can reference clean, attributed numbers
instead of re-parsing free-text findings. Each QuantMetric keeps a URL back to
the source + one to two sentences of surrounding context, so later layers
(Analyst, Contrarian Pass, Writer) can cite without re-fetching.

Input:  cell name + its ScoutResult list (same shape Analyst receives)
Output: list[QuantMetric]

Failure mode: on LLM error or schema mismatch we return an empty list — the
Analyst still works, it just loses the structured-numbers crutch. Never raises.
"""
from __future__ import annotations

import json
import logging

from pydantic import BaseModel, Field

from config import model_for
from llm import call_json
from models import QuantMetric, ScoutResult

log = logging.getLogger("quant_extractor")


class _ExtractorOutput(BaseModel):
    metrics: list[QuantMetric] = Field(default_factory=list)


_SYSTEM = """Ты — экстрактор численных метрик. Тебе дают findings по одной ячейке исследования (домен × слой). Твоя задача — вытащить КАЖДУЮ конкретную цифру, превратить её в структурированную метрику и привязать к источнику.

СТРОГИЕ ПРАВИЛА:
1. Никаких выдуманных чисел. Только то, что дословно есть в `numeric_values` / `verbatim_quote` / `claim` findings.
2. Одна метрика = одно число. «15.7% рост и $2.4B выручки» — это ДВЕ метрики.
3. `name` = что именно измеряется («премия за близость школы», «CTR по premium-сегменту», «доля ипотечных сделок»). Пиши по-русски.
4. `value` = значение с единицей дословно («15.7%», «$2.4B», «n=1842», «3–7%», «Q3 2024»). Диапазоны оставляй как диапазоны.
5. `unit` = чистая единица: `%`, `USD`, `RUB`, `count`, `x`, `ratio`, `year`, `people`, `m²`, …
6. `context` = 1–2 предложения вокруг числа ДОСЛОВНО из источника (verbatim_quote или claim).
7. `confidence`: high — primary_academic/primary_official с явной методологией; medium — отраслевая аналитика с источником; low — вторичный пересказ без верификации.
8. `bias_type`: `validated` — peer-reviewed / independent replication; `vendor` — данные поставщика о самом себе; `aggregation` — сводка поверх других сводок (Statista, СМИ о СМИ); `opinion` — мнение без данных.
9. `source_url` и `source_title` = из поля `source` / `source_label` findings, БЕЗ изменений.
10. Если число дублируется в разных findings — оставь одну метрику с лучшим context.

Если в findings нет ни одного числа — верни `metrics: []`. НЕ ВЫДУМЫВАЙ.

Только JSON по схеме `{"metrics": [...]}`. Русский язык в name и context."""


async def extract_quants(cell: str, scout_results: list[ScoutResult]) -> list[QuantMetric]:
    """Extract structured numeric metrics for a cell. Never raises — returns [] on failure."""
    if not scout_results or not any(sr.findings for sr in scout_results):
        return []

    findings_blob = json.dumps(
        [
            {
                "claim": f.claim,
                "source": f.source,
                "source_label": f.source_label,
                "numeric_values": f.numeric_values,
                "verbatim_quote": f.verbatim_quote,
                "has_numbers": f.has_numbers,
            }
            for sr in scout_results
            for f in sr.findings
        ],
        ensure_ascii=False,
        indent=2,
    )
    # Skip the LLM call if no finding claims to have numbers — saves tokens.
    if not any(
        (f.has_numbers or f.numeric_values)
        for sr in scout_results for f in sr.findings
    ):
        return []

    user = (
        f"Ячейка: {cell}\n\n"
        "Findings из корпуса / Scout'ов:\n"
        f"{findings_blob}\n\n"
        "Верни JSON со списком QuantMetric."
    )
    try:
        result = await call_json(
            model=model_for("analyst"),
            system=_SYSTEM,
            user=user,
            schema=_ExtractorOutput,
            temperature=0.1,
            max_tokens=8000,
        )
    except Exception as exc:
        log.warning("quant_extractor [%s] failed: %s", cell, exc)
        return []

    log.info("quant_extractor [%s]: %d metrics", cell, len(result.metrics))
    return result.metrics
