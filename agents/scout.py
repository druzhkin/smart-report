"""Scout — one ScoutTask → raw search → Finding list."""
from __future__ import annotations

import json
import re
from typing import Any

from config import load_prompt, model_for
from llm import call_json
from models import Finding, ScoutResult, ScoutTask
from pydantic import BaseModel
from search import search

_NUM_RE = re.compile(
    r"(?:"
    # currency-prefixed amounts: $2.4B, ₽450, €1.2M
    r"[$€£¥₽]\s?\d[\d,.]*\s?(?:B|M|K|T|bn|mn|trn|k|млрд|млн|тыс|)?\b"
    # percentages
    r"|\d[\d,.]*\s?(?:%|‰|pp|percent|процент(?:ов|а)?|процентных\sпунктов)\b"
    # time quarters / halves / years
    r"|(?:Q[1-4]|H[12])[\s-]?\d{4}\b"
    r"|\d{4}(?:[-–]\d{2,4})?\b"
    # multiples: 3x, 2.5×, в 4 раза
    r"|\d[\d.]*\s?(?:x|×|fold|кратн[а-я]*|раз[а-я]*)\b"
    # sample sizes: n=1842, N=500
    r"|[nN]\s?=\s?\d[\d,]*\b"
    # counts with units (RU/EN)
    r"|\d[\d,]*\s?(?:человек|пациент(?:ов|а)?|участник(?:ов|а)?|респондент(?:ов|а)?|клиент(?:ов|а)?|сайт(?:ов|а)?|patients?|sites?|subjects?|respondents?)\b"
    # durations
    r"|\d[\d.]*\s?(?:мес(?:яц(?:ев|а)?|\.?)?|год(?:а|ов|\b)?|лет\b|week(?:s)?\b|month(?:s)?\b|day(?:s)?\b|years?\b|days?\b|час(?:а|ов|\b)?)"
    # power/physical units
    r"|\d[\d.]*\s?(?:MW|kW|GW|ГВт|МВт|кВт|Вт|kg|км|mg|°C|°F)\b"
    r")",
    flags=re.IGNORECASE | re.UNICODE,
)


def _extract_numeric_values(text: str, limit: int = 8) -> list[str]:
    """Regex-extract numeric phrases with units from abstract/quote text."""
    if not text:
        return []
    seen: list[str] = []
    for m in _NUM_RE.finditer(text):
        v = m.group(0).strip()
        if len(v) < 2 or v in seen:
            continue
        seen.append(v)
        if len(seen) >= limit:
            break
    return seen

SYSTEM = load_prompt("scout")


class _ScoutPayload(BaseModel):
    findings: list[Finding]
    notes: str | None = None


def _academic_items_to_findings(items: list[dict[str, Any]]) -> list[Finding]:
    """Convert structured academic metadata from search backend into typed Findings.

    These come directly from DOI-backed APIs (OpenAlex / Crossref / S2 / arXiv / PubMed /
    Europe PMC / DOAJ / CORE) so we can label source_type='primary_academic' without
    asking the LLM to guess.
    """
    out: list[Finding] = []
    for it in items[:8]:
        title = (it.get("title") or "").strip()
        if not title:
            continue
        authors = it.get("authors") or []
        venue = it.get("venue") or ""
        year = it.get("year")
        cites = int(it.get("citations") or 0)
        abstract = (it.get("abstract") or "").strip()
        claim_bits = [title]
        if abstract:
            claim_bits.append(abstract[:500])
        claim = " — ".join(claim_bits)[:1200]
        label_parts = []
        if venue:
            label_parts.append(venue)
        if year:
            label_parts.append(str(year))
        label = ", ".join(label_parts) if label_parts else (authors[0] if authors else "academic source")
        has_numbers = bool(abstract) and any(ch.isdigit() for ch in abstract)
        numeric_values = _extract_numeric_values(abstract) if has_numbers else []
        verbatim_quote = (abstract[:400] or None) if has_numbers else None
        entities = [a for a in authors if a][:5]
        if venue:
            entities.append(venue)
        out.append(Finding(
            claim=claim,
            source=it.get("url") or "",
            source_label=label,
            source_type="primary_academic",
            citation_count=cites,
            year=year if isinstance(year, int) else None,
            source_db=it.get("source_db") or "academic",
            has_numbers=has_numbers,
            entities=entities[:8],
            numeric_values=numeric_values,
            verbatim_quote=verbatim_quote,
        ))
    return out


async def scout(task: ScoutTask) -> ScoutResult:
    raw = await search(task.query_focus, focus=task.cell, search_type=task.search_type)
    academic_items = raw.get("academic_items") or []
    academic_findings = _academic_items_to_findings(academic_items)
    web_source_db = raw.get("source_db") or raw.get("fallback") or "web_unknown"

    citations_blob = json.dumps(raw.get("citations", []), ensure_ascii=False, indent=2)
    academic_hint = ""
    if academic_findings:
        academic_hint = (
            "\n\n--- PRE-EXTRACTED ACADEMIC FINDINGS (already typed as primary_academic, "
            "do NOT duplicate in your output) ---\n"
            + json.dumps([f.model_dump() for f in academic_findings], ensure_ascii=False, indent=2)
        )

    user = (
        f"Ячейка: {task.cell}\n"
        f"Задание: {task.query_focus}\n"
        f"Подсказки по источникам: {task.source_hints}\n"
        f"search_type: {task.search_type}\n\n"
        f"--- Сырой результат поиска ---\n{raw.get('text', '')}\n\n"
        f"--- Цитаты / URL ---\n{citations_blob}"
        f"{academic_hint}\n\n"
        "Извлеки находки по контракту из system prompt. "
        "Если уже есть pre-extracted академические находки — НЕ копируй их, сосредоточься на "
        "дополнительной фактуре из web-блока (Perplexity/Tavily/Firecrawl). Только JSON."
    )
    payload = await call_json(
        model=model_for("scout"),
        system=SYSTEM,
        user=user,
        schema=_ScoutPayload,
        temperature=0.2,
    )
    # Ground-truth backend attribution: override whatever the LLM guessed with the
    # actual search backend label. Without this the bench can't tell which backend
    # contributed each finding — the LLM tends to pick familiar enum values (e.g.
    # "firecrawl") regardless of which backend produced the raw text.
    web_findings = list(payload.findings)
    for f in web_findings:
        f.source_db = web_source_db
    findings = list(academic_findings) + web_findings
    return ScoutResult(task=task, findings=findings, notes=payload.notes)
