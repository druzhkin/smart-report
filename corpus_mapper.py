"""One-shot LLM mapping: full Corpus → per-cell findings.

Replaces the per-scout fanout layer. Instead of issuing 42 search queries and
having each scout interpret its own slice, we ask a long-context model to read
the *entire* corpus once and attribute each concrete claim to the right cell(s).

Critical contract (per the Variant E spec):
    Каждый MappedFinding несёт `surrounding_context` — ±2 абзаца вокруг claim.
    Без контекста Analyst строит вывод на вырванной цитате и галлюцинирует.

Output shape:
    dict[cell_name, list[MappedFinding]]

Scaling strategy:
    - gemini-2.5-flash supports ~1M tokens. Typical corpus = 150k words ≈ 200k
      tokens — fits in one call with headroom.
    - Above a safety threshold (~700k tokens of input) we clamp full_text per
      source to keep the prompt under gemini's effective context window.
    - If after clamping we're still over budget, we batch by domain: one LLM
      call per Domain with that domain's cells, so every finding still sees
      the full corpus for its own attribution.
"""
from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from config import model_for
from corpus_fetch import Corpus, CorpusSource
from llm import call_json
from models import Matrix

log = logging.getLogger("corpus_mapper")

# Rough word→token ratio for Russian+English mixed text. Conservative so we
# under-utilise rather than overflow the context window.
_WORDS_PER_TOKEN = 0.75
_TOKEN_BUDGET_SINGLE_CALL = 700_000
_TOKEN_BUDGET_PER_DOMAIN = 250_000

# Per-source full_text cap (chars). Sources already capped at 8000 in fetch;
# we tighten further only if the whole corpus won't fit.
_SOURCE_TEXT_CAP_DEFAULT = 6000
_SOURCE_TEXT_CAP_TIGHT = 2500

# Max output tokens for corpus mapping calls. Sized to handle 15 cells × ~5
# findings × ~500 chars surrounding_context + JSON scaffolding with headroom.
# gemini-2.5-pro supports up to 65535; other tier models (gemini-2.5-flash) also
# support >60k. Fallback to 32000 if the API rejects 60000.
_MAX_TOKENS_SINGLE = 60_000
_MAX_TOKENS_PER_DOMAIN = 60_000
_MAX_TOKENS_FALLBACK = 32_000


# ---------- output models ------------------------------------------------


class MappedFinding(BaseModel):
    claim: str = Field(..., description="Одно фактологическое утверждение, извлечённое из корпуса")
    numbers: list[str] = Field(
        default_factory=list,
        description="Цифры с единицами — '$2.4B', '15.7%', 'n=1842'. Пусто если нет.",
    )
    source_url: str
    source_title: str = ""
    surrounding_context: str = Field(
        default="",
        description="±2 абзаца вокруг claim дословно. Без контекста = галлюцинации аналитика.",
    )
    relevance_score: float = Field(
        default=0.5, ge=0.0, le=1.0,
        description="0..1 — насколько точно finding относится к этой ячейке",
    )
    cross_reference_cells: list[str] = Field(
        default_factory=list,
        description="Другие ячейки, куда этот finding тоже релевантен",
    )


class CellMapping(BaseModel):
    cell: str
    findings: list[MappedFinding] = Field(default_factory=list)


class _MapperOutput(BaseModel):
    mappings: list[CellMapping] = Field(default_factory=list)


# ---------- helpers ------------------------------------------------------


def _cells_from_matrix(matrix: Matrix) -> list[str]:
    if matrix.cell_plans:
        return [cp.cell for cp in matrix.cell_plans]
    return [f"{d.name} / {l.name}" for d in matrix.domains for l in d.layers]


def _approx_tokens(text: str) -> int:
    return int(len((text or "").split()) / _WORDS_PER_TOKEN)


def _render_source(s: CorpusSource, cap: int) -> str:
    body = (s.full_text or s.excerpt or "").strip()
    if len(body) > cap:
        body = body[:cap] + "…"
    meta_bits = [f"backend={s.backend}"]
    if s.year:
        meta_bits.append(f"year={s.year}")
    if s.is_peer_reviewed:
        meta_bits.append("peer_reviewed")
    meta = " | ".join(meta_bits)
    return f"### [{s.title or s.url}]({s.url})\n<{meta}>\n{body}".strip()


def _render_corpus(corpus: Corpus, source_cap: int, include_synth: bool) -> str:
    parts: list[str] = []
    if include_synth and corpus.synth_reports:
        for backend, synth in corpus.synth_reports.items():
            if synth:
                parts.append(f"## Synth report ({backend})\n{synth.strip()}")
    if corpus.sources:
        parts.append("## Sources")
        for s in corpus.sources:
            rendered = _render_source(s, cap=source_cap)
            if rendered:
                parts.append(rendered)
    return "\n\n".join(parts)


def _pick_budget(corpus_text: str) -> tuple[str, bool]:
    """Decide whether full corpus fits; return (corpus_text, needs_domain_batching)."""
    toks = _approx_tokens(corpus_text)
    if toks <= _TOKEN_BUDGET_SINGLE_CALL:
        return corpus_text, False
    log.info("corpus_mapper: %d tokens over single-call budget — switching to per-domain batching", toks)
    return corpus_text, True


def _render_cells(cells: list[str], matrix: Matrix) -> str:
    """Cell list with layer descriptions so the mapper knows what each cell is asking for."""
    layer_desc: dict[str, str] = {}
    for d in matrix.domains:
        for l in d.layers:
            key = f"{d.name} / {l.name}"
            layer_desc[key] = l.description or ""
    lines: list[str] = []
    for c in cells:
        desc = layer_desc.get(c, "")
        lines.append(f"- **{c}** — {desc}" if desc else f"- **{c}**")
    return "\n".join(lines)


# ---------- prompt -------------------------------------------------------


_SYSTEM_PROMPT = """Ты — аналитик-картограф. Тебе дан корпус из нескольких deep-research отчётов и список ячеек матрицы «домен × слой» исследования.

Твоя задача: для каждой ячейки собрать конкретные findings из корпуса. Один finding = одно фактологическое утверждение с цифрами или именованными сущностями, привязанное к одному источнику.

СТРОГИЕ ПРАВИЛА:
1. Никаких выдуманных фактов. Только то, что есть в корпусе дословно.
2. Для КАЖДОГО finding обязательно `surrounding_context` — ±2 абзаца дословно из источника вокруг этого утверждения (или весь источник, если он короче). Без контекста finding бесполезен.
3. Предпочитай findings с цифрами (суммы, проценты, даты, размеры выборки). Извлекай числа в поле `numbers` как строки с единицами: «$2.4B», «15.7%», «n=1842», «Q3 2024».
4. Один finding может относиться к нескольким ячейкам — укажи основную в `cell`, остальные в `cross_reference_cells`.
5. `relevance_score` (0..1): 1.0 = finding прямо отвечает на вопрос ячейки; 0.5 = касается по касательной; <0.3 — не включай вовсе.
6. Если для ячейки нет findings из отдельных источников (поле full_text пустое), но есть синтез-отчёты («Synth report (backend)»), — ИЗВЛЕКАЙ findings из синтез-отчётов. Это не выдумка: синтез-отчёт — продукт самого deep-research бэкенда по реальным источникам. Используй `source_url = "synth://<backend>"` и `source_title = "Synth report (<backend>)"`. Отдавай предпочтение конкретным источникам (если есть), синтез — это запасной вариант.
7. Источник из отдельного источника — URL и title из корпуса. Не сокращай URL.
8. Для findings, извлечённых из синтез-отчёта, `surrounding_context` = ~300 символов текста синтеза вокруг утверждения (не требуется ±2 абзаца из первоисточника — у нас его нет). Для findings из отдельных источников — ±2 абзаца как обычно.

Выход строго в JSON-схеме MapperOutput. Русский язык."""


_USER_TEMPLATE = """# Цель исследования
{goal}

# Ячейки матрицы (куда раскладывать findings)
{cells_block}

# Корпус
{corpus_block}

---

Сопоставь findings с ячейками. Для каждой ячейки — отдельный CellMapping в `mappings`. Если для ячейки ничего подходящего нет, верни её с пустым `findings: []`.

Формат вывода:
{{
  "mappings": [
    {{
      "cell": "Domain / Layer",
      "findings": [
        {{
          "claim": "...",
          "numbers": ["..."],
          "source_url": "https://...",
          "source_title": "...",
          "surrounding_context": "параграф до\\n\\nцитата\\n\\nпараграф после",
          "relevance_score": 0.9,
          "cross_reference_cells": ["Другой домен / Слой"]
        }}
      ]
    }}
  ]
}}"""


# ---------- main entry point --------------------------------------------


async def map_corpus_to_cells(
    corpus: Corpus,
    matrix: Matrix,
    *,
    model: str | None = None,
) -> dict[str, list[MappedFinding]]:
    """Map corpus to per-cell findings in one LLM call (or batched by domain)."""
    cells = _cells_from_matrix(matrix)
    if not cells:
        return {}
    if not corpus.sources and not corpus.synth_reports:
        log.warning("corpus_mapper: empty corpus — returning empty mapping")
        return {c: [] for c in cells}

    # Mapper emits structured JSON (Pydantic schema). gemini-2.5-pro is JSON-fragile on
    # nested schemas — use the profile's mapper_model (Flash by default), NOT analyst_model.
    model_id = model or model_for("mapper")

    corpus_text = _render_corpus(corpus, source_cap=_SOURCE_TEXT_CAP_DEFAULT, include_synth=True)
    _, needs_batching = _pick_budget(corpus_text)

    if needs_batching:
        corpus_text = _render_corpus(corpus, source_cap=_SOURCE_TEXT_CAP_TIGHT, include_synth=True)

    if not needs_batching:
        result = await _single_call(corpus_text, cells, matrix, model_id)
        # Zero-finding safety net: if single-call returned nothing, retry with
        # per-domain batching once — cheap insurance against flaky LLM responses.
        total = sum(len(v) for v in result.values())
        if total == 0 and corpus.sources or (not corpus.sources and corpus.synth_reports):
            log.warning(
                "corpus_mapper: single-call returned 0 findings — retrying with per-domain batching"
            )
            result = await _per_domain_call(corpus_text, matrix, model_id)
        return result

    return await _per_domain_call(corpus_text, matrix, model_id)


async def _call_json_with_fallback(
    *,
    model_id: str,
    user: str,
    max_tokens: int,
    label: str,
) -> _MapperOutput:
    """Invoke call_json with max_tokens; fall back to _MAX_TOKENS_FALLBACK if the API rejects it."""
    log.info(
        "corpus_mapper: %s input=%d chars (≈%d tok)",
        label,
        len(user),
        _approx_tokens(user),
    )
    try:
        return await call_json(
            model=model_id,
            system=_SYSTEM_PROMPT,
            user=user,
            schema=_MapperOutput,
            temperature=0.2,
            max_tokens=max_tokens,
        )
    except Exception as exc:
        # If the error looks like a max_tokens cap rejection, retry at fallback value.
        err_str = str(exc).lower()
        if max_tokens > _MAX_TOKENS_FALLBACK and (
            "max_tokens" in err_str or "maximum" in err_str or "output" in err_str
        ):
            log.warning(
                "corpus_mapper: %s max_tokens=%d rejected (%s: %s) — retrying at %d",
                label,
                max_tokens,
                type(exc).__name__,
                exc,
                _MAX_TOKENS_FALLBACK,
            )
            return await call_json(
                model=model_id,
                system=_SYSTEM_PROMPT,
                user=user,
                schema=_MapperOutput,
                temperature=0.2,
                max_tokens=_MAX_TOKENS_FALLBACK,
            )
        raise


async def _single_call(
    corpus_text: str,
    cells: list[str],
    matrix: Matrix,
    model_id: str,
) -> dict[str, list[MappedFinding]]:
    cells_block = _render_cells(cells, matrix)
    user = _USER_TEMPLATE.format(goal=matrix.goal, cells_block=cells_block, corpus_block=corpus_text)
    try:
        result = await _call_json_with_fallback(
            model_id=model_id,
            user=user,
            max_tokens=_MAX_TOKENS_SINGLE,
            label=f"single-call cells={len(cells)}",
        )
    except Exception as exc:
        log.warning(
            "corpus_mapper: single-call failed (%s: %s) — returning empty mapping",
            type(exc).__name__,
            exc,
        )
        return {c: [] for c in cells}

    return _collect(result, cells)


async def _per_domain_call(
    corpus_text: str,
    matrix: Matrix,
    model_id: str,
) -> dict[str, list[MappedFinding]]:
    """Run one mapping call per domain — each sees the full corpus, limited cells."""
    import asyncio

    per_domain_tasks: list[tuple[list[str], Any]] = []
    for d in matrix.domains:
        cells = [f"{d.name} / {l.name}" for l in d.layers]
        cells_block = _render_cells(cells, matrix)
        user = _USER_TEMPLATE.format(goal=matrix.goal, cells_block=cells_block, corpus_block=corpus_text)
        task = asyncio.create_task(
            _call_json_with_fallback(
                model_id=model_id,
                user=user,
                max_tokens=_MAX_TOKENS_PER_DOMAIN,
                label=f"domain={d.name!r} cells={len(cells)}",
            )
        )
        per_domain_tasks.append((cells, task))

    merged: dict[str, list[MappedFinding]] = {}
    for cells, task in per_domain_tasks:
        try:
            result = await task
        except Exception as exc:
            log.warning(
                "corpus_mapper: domain batch failed (%s: %s) — skipping",
                type(exc).__name__,
                exc,
            )
            for c in cells:
                merged.setdefault(c, [])
            continue
        partial = _collect(result, cells)
        for c, findings in partial.items():
            merged.setdefault(c, []).extend(findings)
    return merged


def _collect(result: _MapperOutput, cells: list[str]) -> dict[str, list[MappedFinding]]:
    out: dict[str, list[MappedFinding]] = {c: [] for c in cells}
    cell_set = set(cells)

    # Warn if LLM returned mappings that don't match any known cell at all.
    if result.mappings:
        unmatched_before_remap = [m.cell for m in result.mappings if m.cell not in cell_set]
        if len(unmatched_before_remap) == len(result.mappings):
            log.warning(
                "corpus_mapper: LLM returned %d mappings but 0 matched known cells — sample: %r",
                len(result.mappings),
                result.mappings[:2],
            )

    for m in result.mappings:
        if m.cell in cell_set:
            out[m.cell].extend(m.findings)
        else:
            best = _closest_cell(m.cell, cells)
            if best:
                out[best].extend(m.findings)
                log.debug("corpus_mapper: remapped %r → %r", m.cell, best)

    total = sum(len(v) for v in out.values())
    log.info("corpus_mapper: cells=%d total_findings=%d", len(out), total)

    # Per-cell breakdown at DEBUG level.
    for cell, findings in out.items():
        log.debug("corpus_mapper: cell %r → %d findings", cell, len(findings))

    return out


def _closest_cell(needle: str, cells: list[str]) -> str | None:
    """Tolerant match — model sometimes returns minor variations on the cell label.

    Preference order:
    1. Exact match (case-insensitive) — already done by caller before this is invoked.
    2. Exact prefix match: needle starts with the cell name or vice versa.
    3. Substring match: either string contained in the other.
    """
    n = needle.strip().lower()
    # Exact (case-insensitive) — handled by caller, but guard here too.
    for c in cells:
        if c.strip().lower() == n:
            return c
    # Exact prefix match — avoids "Facade" matching both "Facade design / Impact"
    # and "Facade impact / Price" when one is a true prefix of the needle.
    for c in cells:
        cl = c.strip().lower()
        if cl.startswith(n) or n.startswith(cl):
            return c
    # Substring fallback.
    for c in cells:
        cl = c.strip().lower()
        if n in cl or cl in n:
            return c
    return None
