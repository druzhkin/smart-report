"""Analyzer — 2nd of three v4 Opus-4.7 reasoning steps.

Takes a question + the research_prompt used + 2–4 uploaded markdown reports
(produced by the analyst pasting the prompt into Perplexity DR / OpenAI DR /
Claude) and returns an AnalysisOutput: per-source summaries, consensus,
conflicts, gaps, unverified numbers, followup-prompts for round 2, quality
notes.

No retrieval here — analyzer only reads what the analyst uploaded.
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
    ConsensusClaim,
    Conflict,
    FollowupPrompt,
    Gap,
    ResearchPrompt,
    SourceSummary,
    UnverifiedNumber,
    UploadedMarkdown,
)


# v4 spec §7 rule 2: Opus 4.7, don't swap.
ANALYZER_MODEL = "anthropic/claude-opus-4-7"
_MAX_JSON_RETRIES = 2


async def analyze_reports(
    question: str,
    research_prompt: ResearchPrompt | None,
    source_reports: list[UploadedMarkdown],
    *,
    emitter: EventEmitter | None = None,
    log_dir: Path | None = None,
    mock: bool = False,
) -> AnalysisOutput:
    """Run the Analyzer over uploaded source reports.

    Caller (v4_orchestrator) owns session-state attachment and cost accounting.
    """
    em: EventEmitter = emitter or NullEmitter()
    q = (question or "").strip()
    if not q:
        raise ValueError("question must be non-empty")
    if not source_reports:
        raise ValueError("source_reports must be non-empty — nothing to analyze")

    em.emit(
        "analyzer",
        f"Анализирую {len(source_reports)} отчётов",
        data={"n_reports": len(source_reports)},
    )

    system = load_prompt("analyzer")
    if not system:
        raise RuntimeError("prompts/analyzer.md not found")

    user = _build_user_message(q, research_prompt, source_reports)

    data = await _call_analyzer_with_retry(
        system=system,
        user=user,
        log_dir=log_dir,
        mock=mock,
    )

    out = _coerce_analysis(data)

    em.emit(
        "analyzer",
        "Анализ готов",
        data={
            "consensus": len(out.consensus),
            "conflicts": len(out.conflicts),
            "gaps": len(out.gaps),
            "followup_prompts": len(out.followup_prompts),
            "unverified_numbers": len(out.unverified_numbers),
        },
    )
    return out


def _build_user_message(
    question: str,
    research_prompt: ResearchPrompt | None,
    reports: list[UploadedMarkdown],
) -> str:
    parts: list[str] = [
        f"## Original analyst question\n{question}\n",
    ]
    if research_prompt is not None:
        parts.append(
            "## Research prompt that produced these reports\n"
            f"{research_prompt.full_prompt}\n"
        )
    parts.append(f"## Source reports (n={len(reports)})\n")
    for i, r in enumerate(reports, start=1):
        header = (
            f"### [{i}] filename={r.filename} "
            f"detected_tool={r.detected_tool or 'unknown'} "
            f"words={r.word_count}"
        )
        parts.append(header)
        parts.append(r.content.strip() + "\n")
    parts.append(
        "\n---\n"
        "Return STRICT JSON matching the AnalysisOutput schema from your system "
        "prompt. No prose wrapper. No markdown fences."
    )
    return "\n".join(parts)


async def _call_analyzer_with_retry(
    *, system: str, user: str, log_dir: Path | None, mock: bool
) -> dict[str, Any]:
    last_err: Exception | None = None
    for attempt in range(_MAX_JSON_RETRIES + 1):
        raw = await chat(
            role="analyzer",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            model=ANALYZER_MODEL,
            temperature=0.3,
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
                f"Analyzer returned non-object JSON: {type(data).__name__}"
            )
            if attempt < _MAX_JSON_RETRIES:
                continue
            raise last_err
        return data
    assert last_err is not None
    raise last_err


def _coerce_analysis(data: dict[str, Any]) -> AnalysisOutput:
    """Build AnalysisOutput from loose LLM JSON, tolerating missing fields.

    Anything critical missing → reasonable default, not an exception. Downstream
    consumers (synthesizer, UI) gate on field content, so we don't want a
    partially-structured response to blow up the whole run.
    """
    per_source = [
        SourceSummary(
            source=_s(item, "source"),
            summary=_s(item, "summary"),
            strengths=_s(item, "strengths"),
            weaknesses=_s(item, "weaknesses"),
        )
        for item in _as_dict_list(data.get("per_source_summary"))
        if _s(item, "source") or _s(item, "summary")
    ]
    consensus = [
        ConsensusClaim(
            claim=_s(item, "claim"),
            supporting_sources=_as_str_list(item.get("supporting_sources")),
            confidence=_enum(item.get("confidence"), ("high", "medium", "low"), "medium"),
        )
        for item in _as_dict_list(data.get("consensus"))
        if _s(item, "claim")
    ]
    conflicts = [
        Conflict(
            topic=_s(item, "topic"),
            source_a=_s(item, "source_a"),
            claim_a=_s(item, "claim_a"),
            source_b=_s(item, "source_b"),
            claim_b=_s(item, "claim_b"),
            resolution_hint=_s(item, "resolution_hint"),
            importance=_enum(
                item.get("importance"), ("critical", "material", "minor"), "material"
            ),
        )
        for item in _as_dict_list(data.get("conflicts"))
        if _s(item, "topic")
    ]
    gaps = [
        Gap(
            topic=_s(item, "topic"),
            why_critical=_s(item, "why_critical"),
            what_to_find=_s(item, "what_to_find"),
            candidate_sources=_as_str_list(item.get("candidate_sources")),
        )
        for item in _as_dict_list(data.get("gaps"))
        if _s(item, "topic")
    ]
    unverified = [
        UnverifiedNumber(
            value=_s(item, "value"),
            metric=_s(item, "metric"),
            subject=_s(item, "subject"),
            source_tool=_s(item, "source_tool"),
            why_unverified=_s(item, "why_unverified"),
        )
        for item in _as_dict_list(data.get("unverified_numbers"))
        if _s(item, "value")
    ]
    followups_raw = _as_dict_list(data.get("followup_prompts"))
    followups: list[FollowupPrompt] = []
    for i, item in enumerate(followups_raw, start=1):
        prompt_text = _s(item, "prompt")
        if not prompt_text:
            continue
        pid = _s(item, "prompt_id") or f"fp_{i:02d}"
        followups.append(
            FollowupPrompt(
                prompt_id=pid,
                intent=_enum(
                    item.get("intent"),
                    ("fill_gap", "verify_number", "resolve_conflict"),
                    "fill_gap",
                ),
                prompt=prompt_text,
                target_info=_s(item, "target_info"),
                suggested_tool=_enum(
                    item.get("suggested_tool"),
                    ("perplexity", "openai_dr", "claude"),
                    "perplexity",
                ),
                suggested_source_site=_s(item, "suggested_source_site"),
                priority=_enum(item.get("priority"), ("must", "nice"), "must"),
                linked_to=_s(item, "linked_to"),
            )
        )
    # Cap at 8 (prompt says so, defensive on noisy LLM output).
    followups = followups[:8]
    return AnalysisOutput(
        per_source_summary=per_source,
        consensus=consensus,
        conflicts=conflicts,
        gaps=gaps,
        unverified_numbers=unverified,
        quality_notes=_s(data, "quality_notes"),
        followup_prompts=followups,
    )


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
