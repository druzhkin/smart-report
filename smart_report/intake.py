"""Intake — parse uploaded markdown files into NormalizedReport.

Responsibilities:
1. Extract all inline citations in 4 formats:
   - [[N]](url)          Amenities format
   - citeturnXviewY      OpenAI DR opaque tokens
   - [N] + bibliography  Numbered reference + end-of-doc list
   - [text](url)         Plain markdown links
2. For each source markdown, extract ALL numeric facts via LLM.
3. Populate extracted_sources_inventory (dedup by url).
4. Assess relevance_to_question against the research_prompt.

Target: 200–1000 NumericFact per ~500-line source document.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .events import EventEmitter, NullEmitter
from .io import extract_json, load_prompt
from .llm import LLMResult, call_json
from .models import (
    Claim,
    NormalizedReport,
    NumericFact,
    QualitativeFact,
    SourceRef,
    UploadedMarkdown,
)

# ---------------------------------------------------------------------------
# Regex patterns for 4 citation formats
# ---------------------------------------------------------------------------

# Format 1: [[N]](url) — amenities-main format
_RE_BRACKET_PAREN = re.compile(r"\[\[(\d+)\]\]\(([^)]+)\)")

# Format 2: citeturnXviewY — OpenAI DR opaque tokens (various shapes)
_RE_CITETURN = re.compile(r"(citeturn\w+)")

# Format 3: [N] inline reference (digits only, 1-3 digits)
_RE_INLINE_REF = re.compile(r"\[(\d{1,3})\](?!\()")  # not followed by (

# Format 4: plain markdown links [text](url)
_RE_MD_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

# End-of-document bibliography line: "N. Title — url" or "N. url" or "[N] url"
_RE_BIB_LINE = re.compile(
    r"^\s*(?:\[?(\d{1,3})\]?\.?\s+)"  # leading [N]. or N.
    r"(.+?)$",
    re.MULTILINE,
)

INTAKE_MODEL = "anthropic/claude-opus-4-7"
_MAX_JSON_RETRIES = 2

# ---------------------------------------------------------------------------
# Citation extraction (pure regex, no LLM)
# ---------------------------------------------------------------------------


def extract_sources_from_markdown(content: str, filename: str) -> list[SourceRef]:
    """Parse a markdown document and return all SourceRef objects found.

    Handles all 4 citation formats; deduplicates by URL.
    """
    sources: dict[str, SourceRef] = {}  # url -> SourceRef

    # Detect accessed_via from filename
    accessed_via = _detect_accessed_via(filename)

    # Build numbered bibliography from end of document (if present)
    bib_map = _parse_end_bibliography(content)

    # Format 1: [[N]](url)
    for m in _RE_BRACKET_PAREN.finditer(content):
        url = m.group(2).strip()
        if url and url not in sources:
            sources[url] = SourceRef(
                url=url,
                accessed_via=accessed_via,
                confidence="primary",
            )

    # Format 2: citeturnXviewY opaque tokens
    for m in _RE_CITETURN.finditer(content):
        token = m.group(1)
        opaque_url = f"opaque:{token}"
        if opaque_url not in sources:
            sources[opaque_url] = SourceRef(
                url=opaque_url,
                title=token,
                accessed_via=accessed_via,
                confidence="secondary",
            )

    # Format 3: [N] inline refs — resolve via bib_map
    for m in _RE_INLINE_REF.finditer(content):
        n = int(m.group(1))
        if n in bib_map:
            url, title = bib_map[n]
            if url not in sources:
                sources[url] = SourceRef(
                    url=url,
                    title=title or None,
                    accessed_via=accessed_via,
                    confidence="primary",
                )

    # Format 4: plain [text](url) — skip [[N]](url) already captured
    for m in _RE_MD_LINK.finditer(content):
        text = m.group(1).strip()
        url = m.group(2).strip()
        # Skip if it looks like a bracket-paren (already captured) or image
        if not url or url.startswith("!") or re.match(r"^\d+$", text):
            continue
        if url.startswith("opaque:"):
            continue
        if url not in sources:
            sources[url] = SourceRef(
                url=url,
                title=text if text and not re.match(r"^\d+$", text) else None,
                accessed_via=accessed_via,
                confidence="secondary",
            )

    # Add any bib_map entries that weren't referenced inline (for complete inventory)
    for n, (url, title) in bib_map.items():
        if url and url not in sources:
            sources[url] = SourceRef(
                url=url,
                title=title or None,
                accessed_via=accessed_via,
                confidence="primary",
            )

    return list(sources.values())


def _detect_accessed_via(filename: str) -> str:
    fn = filename.lower()
    if "perplexity" in fn or "deep-research-report-1" in fn:
        return "perplexity_dr_1"
    if "openai" in fn or "deep-research-report-2" in fn:
        return "openai_dr_1"
    return "manual_upload"


def _parse_end_bibliography(content: str) -> dict[int, tuple[str, str]]:
    """Parse numbered bibliography at the end of a document.

    Looks for patterns like:
      1. Title — https://example.com
      [2] https://example.com — Title
      3. https://example.com

    Returns dict: number -> (url, title).
    """
    bib: dict[int, tuple[str, str]] = {}

    # Find the bibliography section (last third of document usually)
    lines = content.splitlines()
    # Look for the section header
    bib_start = len(lines)
    for i, line in enumerate(lines):
        if re.search(r"(?i)(bibliography|references|источники|список\s*источников|footnotes)", line):
            bib_start = i
            break

    # Scan from bib_start (or last 20% of doc) for numbered lines
    scan_start = min(bib_start, max(0, len(lines) - max(50, len(lines) // 5)))
    url_pattern = re.compile(r"https?://\S+")

    for line in lines[scan_start:]:
        m = re.match(r"^\s*(?:\[?(\d{1,3})\]?[.\s]+)(.+)$", line)
        if not m:
            continue
        n = int(m.group(1))
        rest = m.group(2).strip()
        # Extract URL from rest
        urls = url_pattern.findall(rest)
        if urls:
            url = urls[0].rstrip(".,;)")
            title = url_pattern.sub("", rest).strip().strip("—-–").strip()
            bib[n] = (url, title)

    return bib


def extract_sources_near_claim(
    claim_text: str, content: str, sources_inventory: list[SourceRef]
) -> list[SourceRef]:
    """Find sources near a given claim in the original content.

    Looks for the claim text in the document, then looks for citation markers
    within a window of +/- 200 chars around it.
    Returns matching SourceRef objects from inventory.
    """
    # Build url -> SourceRef lookup
    url_to_ref = {ref.url: ref for ref in sources_inventory}

    # Find claim position
    idx = content.find(claim_text[:80])
    if idx == -1:
        return []

    window = content[max(0, idx - 50) : idx + len(claim_text) + 200]

    found: list[SourceRef] = []

    # Look for [[N]](url) in window
    for m in _RE_BRACKET_PAREN.finditer(window):
        url = m.group(2).strip()
        if url in url_to_ref:
            found.append(url_to_ref[url])

    # Look for plain links [text](url) in window
    for m in _RE_MD_LINK.finditer(window):
        url = m.group(2).strip()
        if url in url_to_ref and url_to_ref[url] not in found:
            found.append(url_to_ref[url])

    return found


# ---------------------------------------------------------------------------
# LLM-based numeric fact extraction
# ---------------------------------------------------------------------------


async def extract_numeric_facts_via_llm(
    content: str,
    filename: str,
    research_prompt: str,
    sources_inventory: list[SourceRef],
    *,
    log_dir: Path | None = None,
    mock: bool = False,
) -> tuple[list[NumericFact], list[QualitativeFact], list[Claim]]:
    """Call Opus to extract all numeric and qualitative facts from a document.

    Returns (numeric_facts, qualitative_facts, claims).
    Each NumericFact gets a deterministic fact_id.
    """
    system = load_prompt("intake")
    if not system:
        system = _default_intake_system_prompt()

    # Chunk large documents to stay within context (approx 3000 lines per chunk)
    chunks = _chunk_content(content, max_lines=2000)
    all_numeric: list[NumericFact] = []
    all_qualitative: list[QualitativeFact] = []
    all_claims: list[Claim] = []
    seen_fact_ids: set[str] = set()

    url_to_ref = {ref.url: ref for ref in sources_inventory}

    for chunk_idx, chunk in enumerate(chunks):
        user = _build_intake_user_message(
            chunk=chunk,
            filename=filename,
            research_prompt=research_prompt,
            chunk_idx=chunk_idx,
            total_chunks=len(chunks),
        )
        try:
            data, _ = await _call_intake_with_retry(
                system=system, user=user, log_dir=log_dir, mock=mock
            )
        except Exception:
            # Don't fail intake on a chunk error; skip and continue
            continue

        # Parse numeric_facts
        for item in _as_dict_list(data.get("numeric_facts")):
            value = _s(item, "value")
            metric = _s(item, "metric")
            subject = _s(item, "subject")
            if not value or not metric:
                continue
            fact_id = NumericFact.make_id(value, metric, subject)
            if fact_id in seen_fact_ids:
                continue
            seen_fact_ids.add(fact_id)

            # Build source refs for this fact
            fact_sources = _resolve_fact_sources(item, url_to_ref, sources_inventory)

            cat_raw = item.get("fact_category", "other")
            valid_cats = (
                "price", "volume", "share", "growth_rate", "capex", "opex",
                "premium_pct", "area", "count", "ratio", "ranking_position", "other"
            )
            cat = cat_raw if cat_raw in valid_cats else "other"

            rel_raw = item.get("relevance_to_question", "medium")
            valid_rel = ("high", "medium", "low", "tangential")
            rel = rel_raw if rel_raw in valid_rel else "medium"

            nf = NumericFact(
                fact_id=fact_id,
                value=value,
                metric=metric,
                subject=subject,
                timeframe=_s(item, "timeframe") or None,
                sources=fact_sources,
                relevance_to_question=rel,  # type: ignore[arg-type]
                fact_category=cat,  # type: ignore[arg-type]
            )
            all_numeric.append(nf)

        # Parse qualitative_facts
        for item in _as_dict_list(data.get("qualitative_facts")):
            statement = _s(item, "statement")
            subject = _s(item, "subject")
            if not statement:
                continue
            fact_id = QualitativeFact.make_id(statement, subject)

            fact_sources = _resolve_fact_sources(item, url_to_ref, sources_inventory)

            qcat_raw = item.get("fact_category", "other")
            valid_qcats = (
                "methodology", "case_study", "analogy", "definition",
                "expert_opinion", "comparison", "trend", "other"
            )
            qcat = qcat_raw if qcat_raw in valid_qcats else "other"

            rel_raw = item.get("relevance_to_question", "medium")
            valid_rel = ("high", "medium", "low", "tangential")
            rel = rel_raw if rel_raw in valid_rel else "medium"

            qf = QualitativeFact(
                fact_id=fact_id,
                statement=statement,
                subject=subject,
                sources=fact_sources,
                relevance_to_question=rel,  # type: ignore[arg-type]
                fact_category=qcat,  # type: ignore[arg-type]
            )
            all_qualitative.append(qf)

        # Parse claims
        for item in _as_dict_list(data.get("claims")):
            text = _s(item, "text")
            if not text:
                continue
            claim_sources = _resolve_fact_sources(item, url_to_ref, sources_inventory)

            ct_raw = item.get("claim_type", "qualitative")
            valid_ct = ("numeric", "qualitative", "comparative", "directional")
            ct = ct_raw if ct_raw in valid_ct else "qualitative"

            cl_raw = item.get("confidence_level", "medium")
            valid_cl = ("high", "medium", "low")
            cl = cl_raw if cl_raw in valid_cl else "medium"

            c = Claim(
                text=text,
                sources=claim_sources,
                claim_type=ct,  # type: ignore[arg-type]
                confidence_level=cl,  # type: ignore[arg-type]
            )
            all_claims.append(c)

    return all_numeric, all_qualitative, all_claims


def _resolve_fact_sources(
    item: dict,
    url_to_ref: dict[str, SourceRef],
    sources_inventory: list[SourceRef],
) -> list[SourceRef]:
    """Resolve source_urls field from LLM output to SourceRef objects."""
    resolved: list[SourceRef] = []
    raw_urls = item.get("source_urls") or []
    if isinstance(raw_urls, str):
        raw_urls = [raw_urls]
    for url in raw_urls:
        if not isinstance(url, str):
            continue
        url = url.strip()
        if url in url_to_ref:
            resolved.append(url_to_ref[url])
        elif url:
            # Create a new SourceRef for URLs the LLM found but we didn't parse
            resolved.append(SourceRef(url=url, confidence="secondary"))
    return resolved


def _chunk_content(content: str, max_lines: int = 2000) -> list[str]:
    """Split content into chunks of at most max_lines lines."""
    lines = content.splitlines(keepends=True)
    if len(lines) <= max_lines:
        return [content]
    chunks = []
    for i in range(0, len(lines), max_lines):
        chunks.append("".join(lines[i : i + max_lines]))
    return chunks


def _build_intake_user_message(
    chunk: str,
    filename: str,
    research_prompt: str,
    chunk_idx: int,
    total_chunks: int,
) -> str:
    parts = [
        f"## Source document\nFilename: {filename}",
        f"Chunk {chunk_idx + 1} of {total_chunks}" if total_chunks > 1 else "",
        "",
        f"## Research question / context\n{research_prompt[:1000]}",
        "",
        "## Document content",
        chunk.strip(),
        "",
        "---",
        "Return STRICT JSON matching the schema in the system prompt. No markdown fences.",
    ]
    return "\n".join(p for p in parts if p is not None)


async def _call_intake_with_retry(
    *, system: str, user: str, log_dir: Path | None, mock: bool
) -> tuple[dict[str, Any], float]:
    last_err: Exception | None = None
    for attempt in range(_MAX_JSON_RETRIES + 1):
        llm_result: LLMResult = await call_json(
            role="intake",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            model=INTAKE_MODEL,
            temperature=0.2,
            mock=mock,
            log_dir=log_dir,
            response_format={"type": "json_object"} if not mock else None,
        )
        try:
            data = extract_json(llm_result.text)
        except (ValueError, json.JSONDecodeError) as err:
            last_err = err
            if attempt < _MAX_JSON_RETRIES:
                continue
            raise
        if not isinstance(data, dict):
            last_err = ValueError(
                f"Intake LLM returned non-object JSON: {type(data).__name__}"
            )
            if attempt < _MAX_JSON_RETRIES:
                continue
            raise last_err
        return data, llm_result.cost_rub
    assert last_err is not None
    raise last_err


def _default_intake_system_prompt() -> str:
    return """# Intake — факт-извлечение

Ты — первый агент пайплайна. Твоя задача: максимально полно извлечь факты из одного research-документа.

## НЕ АГРЕГИРУЙ источники
НЕ АГРЕГИРУЙ источник "РБК" — сохраняй полный URL для каждого inline citation.
НЕ ПРОПУСКАЙ числовые факты — извлекай всё что имеет число+единицу. Релевантность оценишь отдельным полем.
Target: на 500 строк исходника — 200-1000 numeric facts.
Если у claim нет inline citation в исходнике — sources=[] + confidence_level="low".

## Output schema (strict JSON)

```json
{
  "numeric_facts": [
    {
      "value": "55%",
      "metric": "доля ипотеки",
      "subject": "бизнес-класс Москва 2024",
      "timeframe": "2024",
      "fact_category": "share",
      "relevance_to_question": "high",
      "source_urls": ["https://example.com/article"]
    }
  ],
  "qualitative_facts": [
    {
      "statement": "Бассейны требуют профессиональной управляющей компании",
      "subject": "бассейн в жилом комплексе",
      "fact_category": "expert_opinion",
      "relevance_to_question": "medium",
      "source_urls": []
    }
  ],
  "claims": [
    {
      "text": "Средняя ценовая премия от бассейна составляет 2-4%",
      "claim_type": "numeric",
      "confidence_level": "medium",
      "source_urls": ["https://example.com/source"]
    }
  ]
}
```

## fact_category для numeric_facts
price | volume | share | growth_rate | capex | opex | premium_pct | area | count | ratio | ranking_position | other

## fact_category для qualitative_facts
methodology | case_study | analogy | definition | expert_opinion | comparison | trend | other

## relevance_to_question
high — прямо отвечает на вопрос пользователя
medium — косвенно связан
low — фоновая информация
tangential — не относится к теме

Возвращай ТОЛЬКО JSON-объект без markdown-обёртки."""


# ---------------------------------------------------------------------------
# Main public function
# ---------------------------------------------------------------------------


async def normalize_report(
    report: UploadedMarkdown,
    research_prompt: str = "",
    *,
    emitter: EventEmitter | None = None,
    log_dir: Path | None = None,
    mock: bool = False,
) -> NormalizedReport:
    """Parse an UploadedMarkdown into a fully-populated NormalizedReport.

    Steps:
    1. Extract all source URLs via regex (4 formats)
    2. Call LLM to extract numeric + qualitative facts
    3. Return NormalizedReport with complete inventory
    """
    em: EventEmitter = emitter or NullEmitter()
    em.emit(
        "intake",
        f"Нормализую {report.filename}",
        data={"word_count": report.word_count},
    )

    # Step 1: regex-based source extraction
    sources_inventory = extract_sources_from_markdown(report.content, report.filename)

    em.emit(
        "intake",
        "Источники извлечены",
        data={"source_count": len(sources_inventory), "filename": report.filename},
    )

    # Step 2: LLM fact extraction
    numeric_facts, qualitative_facts, claims = await extract_numeric_facts_via_llm(
        content=report.content,
        filename=report.filename,
        research_prompt=research_prompt,
        sources_inventory=sources_inventory,
        log_dir=log_dir,
        mock=mock,
    )

    # Detect source_tool
    source_tool = _detect_source_tool(report.filename, report.detected_tool)

    fact_count_summary = {
        "numeric": len(numeric_facts),
        "qualitative": len(qualitative_facts),
        "claims": len(claims),
        "sources": len(sources_inventory),
    }

    em.emit(
        "intake",
        "Факты извлечены",
        data=fact_count_summary,
    )

    return NormalizedReport(
        source_tool=source_tool,
        source_filename=report.filename,
        raw_text=report.content,
        extracted_claims=claims,
        extracted_sources_inventory=sources_inventory,
        extracted_numeric_facts=numeric_facts,
        extracted_qualitative_facts=qualitative_facts,
        fact_count_summary=fact_count_summary,
        metadata={
            "detected_tool": report.detected_tool,
            "word_count": report.word_count,
        },
    )


def _detect_source_tool(
    filename: str,
    detected_tool: str | None,
) -> str:
    """Map filename/detected_tool to NormalizedReport.source_tool literal."""
    valid = ("perplexity_dr", "openai_dr", "claude_research", "valyu", "other")
    if detected_tool == "perplexity":
        return "perplexity_dr"
    if detected_tool == "openai_dr":
        return "openai_dr"
    if detected_tool == "claude":
        return "claude_research"
    fn = filename.lower()
    if "perplexity" in fn:
        return "perplexity_dr"
    if "openai" in fn:
        return "openai_dr"
    if "claude" in fn:
        return "claude_research"
    return "other"


# ---------------------------------------------------------------------------
# Bulk normalize — runs intake on all source reports in a session
# ---------------------------------------------------------------------------


async def normalize_all_reports(
    reports: list[UploadedMarkdown],
    research_prompt: str = "",
    *,
    emitter: EventEmitter | None = None,
    log_dir: Path | None = None,
    mock: bool = False,
) -> list[NormalizedReport]:
    """Run normalize_report on all uploaded markdown files."""
    results: list[NormalizedReport] = []
    for report in reports:
        nr = await normalize_report(
            report,
            research_prompt=research_prompt,
            emitter=emitter,
            log_dir=log_dir,
            mock=mock,
        )
        results.append(nr)
    return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _s(d: Any, key: str) -> str:
    if not isinstance(d, dict):
        return ""
    v = d.get(key)
    return v.strip() if isinstance(v, str) else ""


def _as_dict_list(v: Any) -> list[dict[str, Any]]:
    if not isinstance(v, list):
        return []
    return [item for item in v if isinstance(item, dict)]
