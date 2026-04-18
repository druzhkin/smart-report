"""v4 pydantic schemas — validate ResearchPrompt, UploadedMarkdown, V4Session."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from smart_report.models import (
    AnalysisOutput,
    FinalReport,
    ResearchPrompt,
    UploadedMarkdown,
    V4Session,
)


def test_research_prompt_minimal() -> None:
    rp = ResearchPrompt(full_prompt="do the thing", reasoning="because")
    assert rp.full_prompt == "do the thing"
    assert rp.key_entities == []
    assert rp.expected_structure == []
    assert rp.tips_for_search == ""


def test_research_prompt_full() -> None:
    rp = ResearchPrompt(
        full_prompt="P",
        reasoning="R",
        expected_structure=["a", "b"],
        key_entities=["PIK", "MR Group"],
        tips_for_search="Perplexity DR",
    )
    assert rp.key_entities == ["PIK", "MR Group"]


def test_research_prompt_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        ResearchPrompt(full_prompt="x", reasoning="y", bogus=1)  # type: ignore[call-arg]


def test_uploaded_markdown_defaults() -> None:
    um = UploadedMarkdown(filename="report.md", content="# hi")
    assert um.detected_tool is None
    assert um.word_count == 0


def test_uploaded_markdown_detected_tool_literal() -> None:
    um = UploadedMarkdown(
        filename="a.md",
        content="body",
        detected_tool="perplexity",
        word_count=12,
    )
    assert um.detected_tool == "perplexity"
    with pytest.raises(ValidationError):
        UploadedMarkdown(
            filename="a.md",
            content="body",
            detected_tool="bard",  # type: ignore[arg-type]
        )


def test_v4_session_minimal() -> None:
    s = V4Session(
        session_id="abc",
        raw_question="what drives developer success",
        created_at=datetime.now(timezone.utc),
    )
    assert s.status == "created"
    assert s.source_reports == []
    assert s.total_cost_rub == 0.0
    assert s.research_prompt is None


def test_v4_session_with_prompt() -> None:
    rp = ResearchPrompt(full_prompt="x" * 250, reasoning="r")
    s = V4Session(
        session_id="abc",
        raw_question="q",
        research_prompt=rp,
        status="prompt_ready",
        created_at=datetime.now(timezone.utc),
    )
    assert s.research_prompt is not None
    assert len(s.research_prompt.full_prompt) == 250


def test_v4_session_rejects_bad_status() -> None:
    with pytest.raises(ValidationError):
        V4Session(
            session_id="abc",
            raw_question="q",
            status="running",  # type: ignore[arg-type]
            created_at=datetime.now(timezone.utc),
        )


def test_v4_session_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        V4Session(
            session_id="abc",
            raw_question="q",
            created_at=datetime.now(timezone.utc),
            extra_field="nope",  # type: ignore[call-arg]
        )


def test_track_b_analysis_output_defaults_empty() -> None:
    # Track B has filled AnalysisOutput with concrete fields; a fresh instance
    # should default-construct with empty collections so Track A endpoints can
    # instantiate it without knowing downstream shape.
    ao = AnalysisOutput()
    dump = ao.model_dump()
    assert dump["consensus"] == []
    assert dump["conflicts"] == []
    assert dump["gaps"] == []


def test_track_b_final_report_requires_exec_summary() -> None:
    # FinalReport is non-trivial now — just confirm session-linkage fields exist
    # so the orchestrator can hand the v4 adapter a valid object.
    with pytest.raises(ValidationError):
        FinalReport(session_id="s", question="q")  # type: ignore[call-arg]
