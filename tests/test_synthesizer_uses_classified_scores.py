"""Tests for v4.5 Phase 3 Step 3.3 Task 3.2 — synthesizer prompt
inclusion of self-assessed source quality scores.

The actual grade-tag override only manifests in live LLM runs (where
the synthesizer obeys the prompt). These mock tests verify that:
  * The classification section appears in the user message
  * Each URL gets its correct deterministic grade (matches Task 3.1)
  * The discipline reminder language is present so the LLM has clear
    instruction to override input-side tags

Mock-only — no LLM call.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from smart_report.models import (
    AnalysisOutput,
    NumericFact,
    QualitativeFact,
    ResearchPrompt,
    SourceRef,
    UploadedMarkdown,
    V4Session,
)
from smart_report.synthesizer import (
    _build_source_quality_section,
    _build_user_message,
)


def _src(url: str, title: str = "") -> SourceRef:
    return SourceRef(url=url, title=title or url, confidence="primary")


def _make_session(
    *,
    raw_question: str,
    sources_in_facts: list[str],
) -> V4Session:
    facts = [
        NumericFact(
            fact_id=NumericFact.make_id(f"v{i}", "m", "s"),
            value=f"v{i}",
            metric="m",
            subject="s",
            sources=[_src(u, f"title {u}")],
        )
        for i, u in enumerate(sources_in_facts)
    ]
    return V4Session(
        session_id="t",
        raw_question=raw_question,
        source_reports=[
            UploadedMarkdown(filename="r.md", content="x", word_count=1)
        ],
        analysis=AnalysisOutput(all_numeric_facts=facts),
        research_prompt=ResearchPrompt(full_prompt="p", reasoning="r"),
        status="analyzed",
        created_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Brief acceptance — the two named tests
# ---------------------------------------------------------------------------


def test_synthesizer_overrides_input_grades():
    """Brief acceptance: source from a Run 1 vendor blog gets WEAK in
    the prompt mapping even though the input markdown might phrase
    the claim confidently. Verifies that the prompt section is built
    with our classification, not the input markdown's grade.
    """
    session = _make_session(
        raw_question="Какие тренды повлияют на девелоперов бизнес-сегмента жилья в Москве в 2026-2027?",
        sources_in_facts=[
            "https://random-blog.ru/devel-trends-2026",  # → WEAK by Step 3.3
        ],
    )
    section = _build_source_quality_section(
        session.analysis, raw_question=session.raw_question
    )
    assert "Smart Report has independently classified" in section
    assert "https://random-blog.ru/devel-trends-2026" in section
    assert "**WEAK**" in section
    # Discipline reminder present
    assert "OVERRIDE" in section


def test_synthesizer_promotes_unmarked_authoritative():
    """Brief acceptance: source from europa.eu — even when input
    markdown didn't pre-tag a grade — gets STRONG in the prompt
    mapping for an EU regulatory query.
    """
    session = _make_session(
        raw_question="How is Direct Air Capture regulated in the EU and what subsidies are available in 2026?",
        sources_in_facts=[
            "https://climate.ec.europa.eu/eu-action/funds",  # → STRONG
            "https://medium.com/@blog/dac-overview",          # → WEAK (forum tier)
        ],
    )
    section = _build_source_quality_section(
        session.analysis, raw_question=session.raw_question
    )
    # europa.eu must be tagged STRONG
    europa_line = next(
        line for line in section.splitlines() if "climate.ec.europa.eu" in line
    )
    assert "**STRONG**" in europa_line
    # medium.com must be tagged WEAK
    medium_line = next(
        line for line in section.splitlines() if "medium.com" in line
    )
    assert "**WEAK**" in medium_line


# ---------------------------------------------------------------------------
# Full integration — section appears in _build_user_message output
# ---------------------------------------------------------------------------


def test_user_message_includes_source_quality_section():
    """The end-to-end check: when synthesizer builds its user message,
    the source-quality section appears alongside facts inventory and
    analysis dump.
    """
    session = _make_session(
        raw_question="Какова доля ипотеки в сегменте жилья бизнес-класса Москвы 2024?",
        sources_in_facts=[
            "https://rosstat.gov.ru/zhilyo-ipoteka-2024.pdf",
            "https://rbc.ru/economy/2024/01/x",
        ],
    )
    user = _build_user_message(session)
    assert "Source quality (self-assessed by Smart Report)" in user
    assert "rosstat.gov.ru" in user
    assert "rbc.ru" in user


def test_user_message_section_skipped_when_no_sources():
    """Empty analysis → no source-quality section (skips cleanly,
    doesn't emit empty header).
    """
    session = _make_session(
        raw_question="Какие тренды повлияют на жильё бизнес-класса в Москве?",
        sources_in_facts=[],  # no sources at all
    )
    user = _build_user_message(session)
    assert "Source quality (self-assessed by Smart Report)" not in user


def test_section_query_domain_label_reflects_detected_domain():
    """The header line must echo the detected query domain so
    analysts reading the prompt trace know which registry was used.
    """
    automotive_session = _make_session(
        raw_question="Сравните перспективы Москвича и АВТОВАЗа на электромобильном рынке 2026-2029",
        sources_in_facts=["https://autostat.ru/x"],
    )
    section = _build_source_quality_section(
        automotive_session.analysis,
        raw_question=automotive_session.raw_question,
    )
    assert "ru_automotive" in section


def test_grades_sorted_strong_first():
    """For readability, the URL list is sorted STRONG → SPECULATIVE so
    the LLM sees the top-tier sources first.
    """
    session = _make_session(
        raw_question="How is the EU AI Act regulated and what are the compliance requirements?",
        sources_in_facts=[
            "https://random-blog.io/x",                # WEAK
            "https://europa.eu/eu-action/policy",      # STRONG
            "https://reuters.com/eu-ai-act",           # MODERATE
        ],
    )
    section = _build_source_quality_section(
        session.analysis, raw_question=session.raw_question
    )
    europa_pos = section.find("europa.eu")
    reuters_pos = section.find("reuters.com")
    blog_pos = section.find("random-blog.io")
    assert europa_pos < reuters_pos < blog_pos, (
        "STRONG should appear before MODERATE before WEAK in the listing"
    )
