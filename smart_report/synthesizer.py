"""Synthesizer — 3rd (final) v4 Opus-4.7 reasoning step.

Takes everything accumulated in a V4Session — question, research_prompt,
source_reports, analysis output, and optional followup_reports — and returns
a FinalReport deeper than any single input.

No retrieval. Works purely on session content.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .events import EventEmitter, NullEmitter
from .io import extract_json, load_prompt
from .llm import chat
from .models import (
    AnalysisOutput,
    ExecutiveSummaryV4,
    FinalReport,
    KeyNumber,
    Source,
    UploadedMarkdown,
    V4Session,
)


SYNTHESIZER_MODEL = "anthropic/claude-opus-4-7"
_MAX_JSON_RETRIES = 2


async def synthesize_final_report(
    session: V4Session,
    *,
    emitter: EventEmitter | None = None,
    log_dir: Path | None = None,
    mock: bool = False,
) -> FinalReport:
    em: EventEmitter = emitter or NullEmitter()
    if not session.source_reports:
        raise ValueError(
            "synthesize_final_report: session has no source_reports; nothing to synthesize"
        )
    if session.analysis is None:
        raise ValueError(
            "synthesize_final_report: session.analysis is None; call analyze first"
        )

    em.emit(
        "synthesizer",
        "Собираю финальный отчёт",
        data={
            "source_reports": len(session.source_reports),
            "followup_reports": len(session.followup_reports),
        },
    )

    system = load_prompt("synthesizer")
    if not system:
        raise RuntimeError("prompts/synthesizer.md not found")

    user = _build_user_message(session)

    data = await _call_synth_with_retry(
        system=system, user=user, log_dir=log_dir, mock=mock
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
        },
    )
    return final


def _build_user_message(session: V4Session) -> str:
    parts: list[str] = [
        f"## Original analyst question\n{session.raw_question}\n",
    ]
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
        parts.append(json.dumps(analysis.model_dump(), ensure_ascii=False, indent=2))
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

    parts.append(
        "\n---\n"
        f"session_id to put back into FinalReport: {session.session_id}\n"
        "Return STRICT JSON matching the FinalReport schema from your system "
        "prompt. No prose wrapper. No markdown fences."
    )
    return "\n".join(parts)


async def _call_synth_with_retry(
    *, system: str, user: str, log_dir: Path | None, mock: bool
) -> dict[str, Any]:
    last_err: Exception | None = None
    for attempt in range(_MAX_JSON_RETRIES + 1):
        raw = await chat(
            role="synthesizer",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            model=SYNTHESIZER_MODEL,
            temperature=0.4,
            mock=mock,
            log_dir=log_dir,
            response_format={"type": "json_object"} if not mock else None,
        )
        try:
            data = extract_json(raw)
        except (ValueError, json.JSONDecodeError) as err:
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
        return data
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
    )


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
