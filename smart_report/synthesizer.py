"""Synthesizer — 3rd (final) v4 Opus-4.7 reasoning step.

Takes everything accumulated in a V4Session — question, research_prompt,
source_reports, analysis output, and optional followup_reports — and returns
a FinalReport deeper than any single input.

No retrieval. Works purely on session content.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .synthesis_critic import ConsistencyReport

from .authoritative_sources import assess_evidence_quality
from .domain_detector import QueryDomain, detect_query_domain
from .events import EventEmitter, NullEmitter
from .io import extract_json, load_prompt
from .llm import LLMResult, call_json
from .source_quality_classifier import classify_source_batch
from .models import (
    AnalysisOutput,
    CalloutBlock,
    ChartSpec,
    ExecutiveSummaryV4,
    FinalReport,
    KeyNumber,
    KeyNumberHighlight,
    QAItem,
    RankingItem,
    Source,
    Table,
    UploadedMarkdown,
    V4Session,
)
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    pass  # AnalysisOutput already imported above


# v4.5 bakeoff winner: Sonnet 4.6 scores 88/100 vs Opus 83/100, 36% cheaper.
# Override via ModelConfig.SYNTHESIZER_MODEL or env var SYNTHESIZER_MODEL.
from .config import ModelConfig as _ModelConfig
SYNTHESIZER_MODEL = _ModelConfig.SYNTHESIZER_MODEL
_MAX_JSON_RETRIES = 2


async def synthesize_final_report(
    session: V4Session,
    *,
    emitter: EventEmitter | None = None,
    log_dir: Path | None = None,
    mock: bool = False,
    consistency_feedback: "ConsistencyReport | None" = None,
    language_feedback: list[Any] | None = None,
    model: str | None = None,
) -> tuple[FinalReport, float]:
    """Generate a FinalReport from the session.

    When ``consistency_feedback`` is provided, the prompt is prefixed with
    critical issues found by the Consistency Critic. When ``language_feedback``
    is provided, the prompt is appended with anglicism warnings from the
    Language Lint. Either retry path must preserve existing content and only
    fix what's flagged.
    """
    em: EventEmitter = emitter or NullEmitter()
    if not session.source_reports:
        raise ValueError(
            "synthesize_final_report: session has no source_reports; nothing to synthesize"
        )
    if session.analysis is None:
        raise ValueError(
            "synthesize_final_report: session.analysis is None; call analyze first"
        )

    is_consistency_retry = consistency_feedback is not None
    is_language_retry = language_feedback is not None
    is_retry = is_consistency_retry or is_language_retry
    em.emit(
        "synthesizer",
        "Собираю финальный отчёт (retry с фидбеком)" if is_retry else "Собираю финальный отчёт",
        data={
            "source_reports": len(session.source_reports),
            "followup_reports": len(session.followup_reports),
            "consistency_retry": is_consistency_retry,
            "language_retry": is_language_retry,
        },
    )

    system = load_prompt("synthesizer")
    if not system:
        raise RuntimeError("prompts/synthesizer.md not found")

    user = _build_user_message(
        session,
        consistency_feedback=consistency_feedback,
        language_feedback=language_feedback,
    )

    data, cost_rub = await _call_synth_with_retry(
        system=system, user=user, log_dir=log_dir, mock=mock, model=model
    )
    final = _coerce_final_report(data, session=session)

    em.emit(
        "synthesizer",
        "Финальный отчёт готов",
        data={
            "main_synthesis_chars": len(final.main_synthesis),
            "key_numbers": len(final.executive_summary.key_numbers),
            "top_findings": len(final.executive_summary.top_findings),
            "sources": len(final.all_sources),
            "qa_section": len(final.qa_section),
            "tables": len(final.tables),
            "charts": len(final.charts),
            "callouts": len(final.callouts),
            "key_numbers_highlight": len(final.key_numbers_highlight),
            "ranking": len(final.ranking),
            "cost_rub": cost_rub,
        },
    )
    return final, cost_rub


def _build_user_message(
    session: V4Session,
    *,
    consistency_feedback: "ConsistencyReport | None" = None,
    language_feedback: list[Any] | None = None,
) -> str:
    parts: list[str] = []

    # Inject consistency critic feedback at the TOP (retry path)
    if consistency_feedback is not None:
        from .synthesis_critic import build_consistency_feedback_text
        feedback_text = build_consistency_feedback_text(consistency_feedback)
        if feedback_text:
            parts.append(f"## КРИТИК: ОБЯЗАТЕЛЬНО ИСПРАВИТЬ\n\n{feedback_text}\n")

    parts.append(f"## Original analyst question\n{session.raw_question}\n")
    if session.research_prompt is not None:
        parts.append(
            "## Research prompt used in round 1\n"
            f"{session.research_prompt.full_prompt}\n"
        )

    parts.append(f"## Source reports (round 1, n={len(session.source_reports)})\n")
    for i, r in enumerate(session.source_reports, start=1):
        parts.append(
            f"### [{i}] filename={r.filename} detected_tool={r.detected_tool or 'unknown'}"
        )
        parts.append(r.content.strip() + "\n")

    analysis = session.analysis
    if analysis is not None:
        parts.append("## Analyzer output (structured JSON)\n")
        parts.append("```json")
        # Exclude fact lists that _build_facts_section injects below in
        # a curated, capped form. Otherwise the prompt double-carries
        # all_numeric_facts (the superset) and high_relevance_facts (the
        # cap-200 subset), inflating realistic 4-fixture runs to 400k+
        # tokens and overflowing 200k-context models like Haiku 4.5.
        # Live Acceptance Run 1 measured 523k chars in the dump alone;
        # this exclude drops it to ~109k while losing zero information
        # the synthesizer actually consumes downstream.
        parts.append(
            json.dumps(
                analysis.model_dump(
                    exclude={"all_numeric_facts", "high_relevance_facts"}
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
        parts.append("```\n")

    if session.followup_reports:
        parts.append(
            f"## Follow-up reports (round 2, dobor, n={len(session.followup_reports)})\n"
        )
        for i, r in enumerate(session.followup_reports, start=1):
            parts.append(
                f"### [fu-{i}] filename={r.filename} detected_tool={r.detected_tool or 'unknown'}"
            )
            parts.append(r.content.strip() + "\n")
    else:
        parts.append(
            "## Follow-up reports\n_No dobor was uploaded. "
            "Gaps remain open — mark them in gaps_filled_section._\n"
        )

    # v4.5: inject fact inventory for data-preservation rule
    if analysis is not None and analysis.all_numeric_facts:
        parts.append(_build_facts_section(analysis))

    # v4.5 Phase 3 Step 3.3: inject self-assessed source quality scores
    # so the synthesizer assigns evidence-grade tags from OUR per-domain
    # classification rather than passively echoing the input markdown's
    # tags. Only fires when analysis carries source URLs.
    if analysis is not None:
        quality_section = _build_source_quality_section(
            analysis, raw_question=session.raw_question
        )
        if quality_section:
            parts.append(quality_section)

    # Language-lint feedback injection (Track 3 retry pass)
    if language_feedback:
        feedback_lines = [
            "\n---",
            "ПРЕДЫДУЩАЯ ВЕРСИЯ СОДЕРЖИТ АНГЛИЦИЗМЫ НЕ ИЗ WHITELIST:",
            "",
        ]
        for warning in language_feedback:
            token = warning.get("token", "") if isinstance(warning, dict) else getattr(warning, "token", "")
            ctx = warning.get("location_context", "") if isinstance(warning, dict) else getattr(warning, "location_context", "")
            feedback_lines.append(f'- "{token}" в контексте "...{ctx}..."')
        feedback_lines.append(
            "\nЗамени каждое на русский эквивалент. Исключения ТОЛЬКО из whitelist выше.\n---"
        )
        parts.append("\n".join(feedback_lines))

    parts.append(
        "\n---\n"
        f"session_id to put back into FinalReport: {session.session_id}\n"
        "Return STRICT JSON matching the FinalReport schema from your system "
        "prompt. No prose wrapper. No markdown fences."
    )
    return "\n".join(parts)


def _build_facts_section(analysis: "AnalysisOutput") -> str:
    """Inject high_relevance_facts and fact_coverage_target into Synthesizer context."""
    import json as _json

    lines = [
        "## v4.5 Fact inventory (DATA PRESERVATION RULE)",
        f"fact_coverage_target = {analysis.fact_coverage_target}",
        f"high_relevance_facts_count = {len(analysis.high_relevance_facts)}",
        f"all_numeric_facts_count = {len(analysis.all_numeric_facts)}",
        "",
        "### high_relevance_facts (must include >= fact_coverage_target of these in final)",
    ]
    # Include up to 200 high-relevance facts to avoid context overload
    facts_to_include = analysis.high_relevance_facts[:200]
    facts_json = [
        {
            "fact_id": nf.fact_id,
            "value": nf.value,
            "metric": nf.metric,
            "subject": nf.subject,
            "timeframe": nf.timeframe,
            "fact_category": nf.fact_category,
            "source_urls": [s.url for s in nf.sources if not s.url.startswith("opaque:")],
        }
        for nf in facts_to_include
    ]
    lines.append("```json")
    lines.append(_json.dumps(facts_json, ensure_ascii=False, indent=2))
    lines.append("```")
    lines.append("")
    lines.append(
        f"IMPORTANT: You MUST include at least {analysis.fact_coverage_target} of the "
        "above high_relevance_facts in your final report. Use [REF:source_url] inline "
        "citations for each numeric fact. If a fact doesn't fit the narrative, add it "
        "to an appendix section 'Дополнительные данные'. "
        "Skipped high-relevance facts > 15% → task failure. "
        "Record skipped facts in metadata.skipped_facts with reason."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Phase 3 Step 3.3 — self-assessed source quality injection
# ---------------------------------------------------------------------------


_MAX_QUALITY_LINES = 80  # cap to keep prompt size predictable


def _build_source_quality_section(
    analysis: "AnalysisOutput", *, raw_question: str
) -> str:
    """Inject Smart Report's deterministic per-URL source-quality grades.

    Run 1 finding 2 was that synthesizer evidence-grade tags were
    inherited from input-markdown wording. This section gives the
    synthesizer OUR per-domain classification (primary_regulator /
    trusted_media / consultancy / forum / unknown) for every source URL
    on the analysis output, so it has authoritative override material
    when prefixing claims with [STRONG] / [MODERATE] / [WEAK] /
    [SPECULATIVE].

    Returns empty string when no source URLs are present.
    """
    # Collect unique URLs across numeric + qualitative facts
    urls: list[str] = []
    seen: set[str] = set()
    for fact in (*analysis.all_numeric_facts, *analysis.all_qualitative_facts):
        for src in fact.sources:
            u = (src.url or "").strip()
            if u and u not in seen and not u.startswith("opaque:"):
                seen.add(u)
                urls.append(u)
    if not urls:
        return ""

    query_domain = detect_query_domain(raw_question)
    scores = classify_source_batch(urls, query_domain)

    # Order: STRONG → MODERATE → WEAK → SPECULATIVE for readability
    strength_order = {"STRONG": 0, "MODERATE": 1, "WEAK": 2, "SPECULATIVE": 3}
    sorted_scores = sorted(
        scores.values(),
        key=lambda s: (strength_order[s.evidence_strength], s.url),
    )

    lines = [
        "## v4.5 Source quality (self-assessed by Smart Report)",
        "",
        f"Detected query domain: **{query_domain.value}**",
        "",
        "Smart Report has independently classified every retrieved source "
        "URL by domain authority (NOT inherited from input-markdown wording). "
        "Use this mapping when prefixing claims with `[STRONG]` / `[MODERATE]` "
        "/ `[WEAK]` / `[SPECULATIVE]` tags — the URL → grade entries below "
        "OVERRIDE any conflicting grade hint from the source reports.",
        "",
        "Mapping (URL → evidence_strength · domain_authority · rationale):",
    ]
    for s in sorted_scores[:_MAX_QUALITY_LINES]:
        lines.append(
            f"- `{s.url}` → **{s.evidence_strength}** "
            f"({s.domain_authority}) — {s.rationale}"
        )
    if len(sorted_scores) > _MAX_QUALITY_LINES:
        lines.append(
            f"…and {len(sorted_scores) - _MAX_QUALITY_LINES} more sources "
            "(same classification rules apply; default to **WEAK** if URL "
            "not listed above)."
        )
    lines.append("")
    lines.append(
        "Discipline reminder: a claim cited from a source listed as "
        "**WEAK** here MUST get a `[WEAK]` tag in your output even if "
        "the input markdown phrased it confidently. Conversely, a claim "
        "cited from a **STRONG** source gets `[STRONG]` even if the "
        "input markdown didn't pre-tag it."
    )
    return "\n".join(lines)


async def _call_synth_with_retry(
    *, system: str, user: str, log_dir: Path | None, mock: bool, model: str | None = None
) -> tuple[dict[str, Any], float]:
    """Call the synthesizer LLM with retry; return ``(parsed_dict, cost_rub)``.

    On each retry temperature drops (0.4 → 0.2 → 0.05). Lower temperature
    means less creative deviation from strict-JSON output format — Opus at
    temp=0.4 on long Russian contexts consistently drops unescaped quotes
    mid-string; at temp=0.05 this disappears.

    Malformed responses are ALWAYS saved to runs/malformed_llm/<ts>_<attempt>.txt
    regardless of log_dir setting, so future diagnosis has raw material without
    re-running the expensive LLM call.

    cost_rub is accumulated across ALL attempts (failed and successful) because
    OpenRouter charges on completion, not on validity. Silent discard of cost
    from failed attempts was previously hiding real spend from session accounting.
    """
    from datetime import datetime as _dt
    from pathlib import Path as _Path

    _temps = [0.4, 0.2, 0.05]  # ramp-down on retries
    total_cost = 0.0
    last_err: Exception | None = None
    for attempt in range(_MAX_JSON_RETRIES + 1):
        temp = _temps[attempt] if attempt < len(_temps) else _temps[-1]
        llm_result: LLMResult = await call_json(
            role="synthesizer",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            model=model or SYNTHESIZER_MODEL,
            temperature=temp,
            mock=mock,
            log_dir=log_dir,
            response_format={"type": "json_object"} if not mock else None,
            # 32k tokens required for FinalReport — 14k causes JSON truncation
            max_tokens=32000,
        )
        total_cost += llm_result.cost_rub
        try:
            data = extract_json(llm_result.text)
        except (ValueError, json.JSONDecodeError) as err:
            # ALWAYS save malformed response for post-mortem (no LLM re-cost to diagnose)
            try:
                dump_dir = _Path("runs") / "malformed_llm"
                dump_dir.mkdir(parents=True, exist_ok=True)
                ts = _dt.utcnow().strftime("%Y%m%dT%H%M%SZ")
                _active_model = model or SYNTHESIZER_MODEL
                dump_path = dump_dir / f"{ts}_attempt{attempt}_{_active_model.replace('/', '_')}.txt"
                dump_path.write_text(
                    f"# error: {err!r}\n# model: {_active_model}\n# temp: {temp}\n# attempt: {attempt}\n# cost_this_call: {llm_result.cost_rub}\n# total_cost_so_far: {total_cost}\n\n{llm_result.text}",
                    encoding="utf-8",
                )
            except Exception:
                pass  # never let dump failure mask the original error
            last_err = err
            if attempt < _MAX_JSON_RETRIES:
                continue
            raise
        if not isinstance(data, dict):
            last_err = ValueError(
                f"Synthesizer returned non-object JSON: {type(data).__name__}"
            )
            if attempt < _MAX_JSON_RETRIES:
                continue
            raise last_err
        return data, total_cost  # return ACCUMULATED cost, not just last attempt's
    assert last_err is not None
    raise last_err


def _coerce_final_report(data: dict[str, Any], *, session: V4Session) -> FinalReport:
    exec_raw = data.get("executive_summary") or {}
    if not isinstance(exec_raw, dict):
        exec_raw = {}

    key_numbers = [
        KeyNumber(
            value=_s(item, "value"),
            metric=_s(item, "metric"),
            subject=_s(item, "subject"),
            source_url=_s(item, "source_url"),
        )
        for item in _as_dict_list(exec_raw.get("key_numbers"))
        if _s(item, "value")
    ]

    top_findings = _as_str_list(exec_raw.get("top_findings"))
    ranking = exec_raw.get("ranking")
    if not isinstance(ranking, str) or not ranking.strip():
        ranking = None

    exec_summary = ExecutiveSummaryV4(
        main_answer=_s(exec_raw, "main_answer"),
        ranking=ranking,
        top_findings=top_findings,
        key_numbers=key_numbers,
        confidence_note=_s(exec_raw, "confidence_note"),
        what_meta_adds=_s(exec_raw, "what_meta_adds"),
    )

    all_sources = [
        Source(
            title=_s(item, "title") or _s(item, "url"),
            url=_s(item, "url"),
            tool=_s(item, "tool"),
            reliability=_enum(
                item.get("reliability"), ("high", "medium", "low"), "medium"
            ),
        )
        for item in _as_dict_list(data.get("all_sources"))
        if _s(item, "title") or _s(item, "url")
    ]

    meta = data.get("metadata")
    if not isinstance(meta, dict):
        meta = {}
    # Add our own authoritative counts — LLM numbers here are often off.
    analysis: AnalysisOutput | None = session.analysis
    meta.setdefault("source_reports_count", len(session.source_reports))
    meta.setdefault("followup_reports_count", len(session.followup_reports))
    if analysis is not None:
        meta.setdefault("consensus_count", len(analysis.consensus))
        meta.setdefault("conflicts_count", len(analysis.conflicts))
        meta.setdefault("gaps_count", len(analysis.gaps))
    meta.setdefault("cost_rub_accumulated", round(session.total_cost_rub, 4))

    # v4.5 Phase 1 Step 1.2 — source-adequacy heuristic. When fewer than
    # the threshold of authoritative RU RE domains are present, mark the
    # report and prefix the warning into confidence_note so every
    # downstream renderer surfaces it without needing per-renderer code.
    quality, warning = assess_evidence_quality(all_sources)
    meta["evidence_quality"] = quality
    if warning:
        meta["evidence_warning"] = warning
        prior_note = exec_summary.confidence_note
        merged_note = warning if not prior_note else f"{warning}\n\n{prior_note}"
        exec_summary = exec_summary.model_copy(update={"confidence_note": merged_note})

    # --- NEW structured output fields ---
    qa_section = _coerce_qa_section(data.get("qa_section"))
    ranking = _coerce_ranking(data.get("ranking"))
    tables = _coerce_tables(data.get("tables"))
    charts = _coerce_charts(data.get("charts"))
    callouts = _coerce_callouts(data.get("callouts"))
    key_numbers_highlight = _coerce_key_numbers_highlight(
        data.get("key_numbers_highlight")
    )
    cover_image_prompt = data.get("cover_image_prompt")
    if not isinstance(cover_image_prompt, str):
        cover_image_prompt = None

    return FinalReport(
        # Session identity is authoritative — LLM echo can drift.
        session_id=session.session_id,
        question=_s(data, "question") or session.raw_question,
        research_prompt_used=_s(data, "research_prompt_used")
        or (session.research_prompt.full_prompt if session.research_prompt else ""),
        executive_summary=exec_summary,
        main_synthesis=_s(data, "main_synthesis"),
        consensus_section=_s(data, "consensus_section"),
        conflicts_section=_s(data, "conflicts_section"),
        gaps_filled_section=_s(data, "gaps_filled_section"),
        all_sources=all_sources,
        metadata=meta,
        # NEW fields
        qa_section=qa_section,
        ranking=ranking,
        tables=tables,
        charts=charts,
        callouts=callouts,
        key_numbers_highlight=key_numbers_highlight,
        cover_image_prompt=cover_image_prompt,
    )


# --- structured output coercers ---


def _coerce_qa_section(v: Any) -> list[QAItem]:
    """Coerce raw LLM list to QAItem list, skipping invalid entries."""
    items = []
    for raw in _as_dict_list(v):
        q = _s(raw, "question")
        a = _s(raw, "answer")
        if q and a:
            items.append(
                QAItem(
                    question=q,
                    answer=a,
                    details_ref=_s(raw, "details_ref"),
                )
            )
    return items


def _coerce_ranking(v: Any) -> list[RankingItem]:
    """Coerce raw LLM list to RankingItem list."""
    items = []
    for raw in _as_dict_list(v):
        label = _s(raw, "label")
        if not label:
            continue
        weight_raw = raw.get("weight")
        weight: int | None = None
        if isinstance(weight_raw, (int, float)) and not isinstance(weight_raw, bool):
            weight = int(weight_raw)
        items.append(
            RankingItem(
                label=label,
                weight=weight,
                rationale=_s(raw, "rationale"),
                evidence_strength=_enum(
                    raw.get("evidence_strength"), ("high", "medium", "low"), "medium"
                ),
            )
        )
    return items


def _coerce_tables(v: Any) -> list[Table]:
    """Coerce raw LLM list to Table list."""
    items = []
    for raw in _as_dict_list(v):
        title = _s(raw, "title")
        columns = _as_str_list(raw.get("columns"))
        rows_raw = raw.get("rows")
        if not title or not columns:
            continue
        rows: list[list[str]] = []
        if isinstance(rows_raw, list):
            for row in rows_raw:
                if isinstance(row, list):
                    rows.append([str(cell) for cell in row])
        caption = raw.get("caption")
        source_ref = raw.get("source_ref")
        items.append(
            Table(
                title=title,
                columns=columns,
                rows=rows,
                caption=caption if isinstance(caption, str) else None,
                source_ref=source_ref if isinstance(source_ref, str) else None,
            )
        )
    return items


def _coerce_charts(v: Any) -> list[ChartSpec]:
    """Coerce raw LLM list to ChartSpec list."""
    _valid_types = ("bar", "line", "pie", "scatter", "stacked_bar", "waterfall")
    items = []
    for raw in _as_dict_list(v):
        chart_type = raw.get("chart_type")
        title = _s(raw, "title")
        data = raw.get("data")
        if chart_type not in _valid_types or not title or not isinstance(data, dict):
            continue
        items.append(
            ChartSpec(
                chart_type=chart_type,  # type: ignore[arg-type]
                title=title,
                data=data,
                x_label=raw.get("x_label") if isinstance(raw.get("x_label"), str) else None,
                y_label=raw.get("y_label") if isinstance(raw.get("y_label"), str) else None,
                caption=raw.get("caption") if isinstance(raw.get("caption"), str) else None,
            )
        )
    return items


def _coerce_callouts(v: Any) -> list[CalloutBlock]:
    """Coerce raw LLM list to CalloutBlock list."""
    _valid_kinds = ("insight", "warning", "key_number", "note")
    items = []
    for raw in _as_dict_list(v):
        kind = raw.get("kind")
        title = _s(raw, "title")
        body = _s(raw, "body")
        if kind not in _valid_kinds or not title or not body:
            continue
        items.append(
            CalloutBlock(
                kind=kind,  # type: ignore[arg-type]
                title=title,
                body=body,
            )
        )
    return items


def _coerce_key_numbers_highlight(v: Any) -> list[KeyNumberHighlight]:
    """Coerce raw LLM list to KeyNumberHighlight list."""
    _valid_importance = ("headline", "primary", "secondary")
    items = []
    for raw in _as_dict_list(v):
        value = _s(raw, "value")
        label = _s(raw, "label")
        if not value or not label:
            continue
        items.append(
            KeyNumberHighlight(
                value=value,
                label=label,
                source_ref=_s(raw, "source_ref"),
                importance=_enum(
                    raw.get("importance"), _valid_importance, "primary"
                ),
            )
        )
    return items


# --- small helpers (mirror analyzer.py style) ---


def _s(d: Any, key: str) -> str:
    if not isinstance(d, dict):
        return ""
    v = d.get(key)
    return v.strip() if isinstance(v, str) else ""


def _as_str_list(v: Any) -> list[str]:
    if not isinstance(v, list):
        return []
    return [s.strip() for s in v if isinstance(s, str) and s.strip()]


def _as_dict_list(v: Any) -> list[dict[str, Any]]:
    if not isinstance(v, list):
        return []
    return [item for item in v if isinstance(item, dict)]


def _enum(v: Any, allowed: tuple[str, ...], default: str) -> Any:
    if isinstance(v, str) and v in allowed:
        return v
    return default


# unused import guard (for tools that can't see analyzer's UploadedMarkdown usage)
_ = UploadedMarkdown


# ---------------------------------------------------------------------------
# Language-lint helper: extract all user-visible text from a FinalReport
# ---------------------------------------------------------------------------


def full_report_text(report: FinalReport) -> str:
    """Concatenate all user-visible text fields from *report* for language linting.

    Deliberately excludes URLs, source titles, and internal metadata so the
    linter focuses on prose authored by the Synthesizer, not on external data.
    """
    parts: list[str] = []

    # Question / title fields
    if report.question:
        parts.append(report.question)

    # Executive summary
    es = report.executive_summary
    if es.main_answer:
        parts.append(es.main_answer)
    parts.extend(es.top_findings)
    if es.confidence_note:
        parts.append(es.confidence_note)
    if es.what_meta_adds:
        parts.append(es.what_meta_adds)
    for kn in es.key_numbers:
        parts.append(kn.metric)
        parts.append(kn.subject)

    # Main body sections
    for field in (
        report.main_synthesis,
        report.consensus_section,
        report.conflicts_section,
        report.gaps_filled_section,
    ):
        if field:
            parts.append(field)

    # Q&A section
    for item in report.qa_section:
        parts.append(item.question)
        parts.append(item.answer)
        if item.details_ref:
            parts.append(item.details_ref)

    # Ranking
    for item in report.ranking:
        parts.append(item.label)
        if item.rationale:
            parts.append(item.rationale)

    # Tables (title + caption + column headers + cell text)
    for table in report.tables:
        parts.append(table.title)
        parts.extend(table.columns)
        for row in table.rows:
            parts.extend(row)
        if table.caption:
            parts.append(table.caption)
        if table.source_ref:
            parts.append(table.source_ref)

    # Charts (title + caption + axis labels)
    for chart in report.charts:
        parts.append(chart.title)
        if chart.x_label:
            parts.append(chart.x_label)
        if chart.y_label:
            parts.append(chart.y_label)
        if chart.caption:
            parts.append(chart.caption)

    # Callouts
    for callout in report.callouts:
        parts.append(callout.title)
        parts.append(callout.body)

    # Key numbers highlight
    for knh in report.key_numbers_highlight:
        parts.append(knh.label)
        parts.append(knh.source_ref)

    return "\n".join(p for p in parts if p)
