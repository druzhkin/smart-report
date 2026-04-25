"""Tests for v4.5 Phase 2 Step 2.3 — gap detection inside the orchestrator.

The integration adds a stage between bibliography post-processing and
coverage audit that mutates the FinalReport with evidence_gaps metadata
and a Cyrillic confidence_note prefix. Mock-only — no LLM calls.
"""

from __future__ import annotations

import pytest

from smart_report.v4_orchestrator import (
    _attach_evidence_gaps,
    _format_gap_warning_for_confidence_note,
)
from smart_report.gap_detector import detect_gaps
from smart_report.i18n import lint_output_language
from smart_report.models import (
    AnalysisOutput,
    EvidenceGap,
    ExecutiveSummaryV4,
    FinalReport,
    NumericFact,
    SourceRef,
    SubQuestion,
)


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _src(url: str, title: str = "") -> SourceRef:
    return SourceRef(url=url, title=title or url, confidence="primary")


def _analysis_with(*sources: tuple[str, str]) -> AnalysisOutput:
    facts = [
        NumericFact(
            fact_id=NumericFact.make_id(f"v{i}", "m", "s"),
            value=f"v{i}",
            metric="m",
            subject="s",
            sources=[_src(u, t)],
        )
        for i, (u, t) in enumerate(sources)
    ]
    return AnalysisOutput(all_numeric_facts=facts)


def _empty_final(*, confidence_note: str = "") -> FinalReport:
    return FinalReport(
        session_id="t",
        question="Q",
        executive_summary=ExecutiveSummaryV4(
            main_answer="ans", confidence_note=confidence_note
        ),
        main_synthesis="body",
    )


def _sq(sid: str, text: str, **kw) -> SubQuestion:
    return SubQuestion(id=sid, text=text, rationale="r", **kw)


class _NullEmitter:
    def emit(self, *a, **kw):
        pass


# ---------------------------------------------------------------------------
# Spec acceptance cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gaps_propagated_to_metadata():
    """Two sub_questions, both unanswered → metadata.evidence_gaps has 2 entries."""
    sub_qs = [
        _sq("sq1", "Какие тренды цен на жильё бизнес-класса Москвы 2024?"),
        _sq("sq2", "Какие риски ставки ЦБ для застройщиков премиум-сегмента?"),
    ]
    # Sources unrelated to either sub_question
    analysis = _analysis_with(
        ("https://github.com/langfuse", "Langfuse observability"),
    )
    final = _empty_final()
    await _attach_evidence_gaps(final, sub_qs, analysis, emitter=_NullEmitter())

    assert "evidence_gaps" in final.metadata
    assert len(final.metadata["evidence_gaps"]) == 2
    assert final.metadata["gap_count_by_severity"] == {
        "critical": 2, "moderate": 0, "minor": 0,
    }


@pytest.mark.asyncio
async def test_no_gaps_no_metadata_pollution():
    """All sub_questions adequately covered → evidence_gaps is empty list,
    confidence_note left untouched.
    """
    sub_qs = [
        _sq("sq1", "Какова доля ипотечных сделок жилья бизнес-класса Москвы 2024?"),
    ]
    analysis = _analysis_with(
        (
            "https://rosstat.gov.ru/zhilyo-ipoteka-biznes-2024.pdf",
            "Доля ипотечных сделок жилья бизнес-класса Москва 2024",
        ),
        (
            "https://erzrf.ru/biznes-zhilyo-ipoteka-statistika-2024",
            "Статистика ипотечных сделок жилья бизнес Москва 2024",
        ),
    )
    final = _empty_final(confidence_note="Доверие высокое.")
    await _attach_evidence_gaps(final, sub_qs, analysis, emitter=_NullEmitter())

    assert final.metadata["evidence_gaps"] == []
    assert final.metadata["gap_count_by_severity"] == {
        "critical": 0, "moderate": 0, "minor": 0,
    }
    # confidence_note left untouched when there are no gaps
    assert final.executive_summary.confidence_note == "Доверие высокое."


@pytest.mark.asyncio
async def test_gaps_in_confidence_note_not_visible_text():
    """Sentinel discipline: the gap warning prefixed onto confidence_note
    must contain ZERO Latin-script tokens — otherwise the language linter
    in the orchestrator's Step 3f will treat it as anglicism noise and
    might trigger a Track 3 retry on the borderline edge (paid lesson 7.2).
    """
    sub_qs = [
        _sq("sq1", "Какие риски рынка жилья при ставке ЦБ?"),
        _sq("sq2", "Какие тренды цен жилья бизнес-класса 2024?"),
    ]
    analysis = _analysis_with()  # zero sources → both critical
    final = _empty_final()
    await _attach_evidence_gaps(final, sub_qs, analysis, emitter=_NullEmitter())

    note = final.executive_summary.confidence_note
    assert note  # warning was added
    # Must contain the Russian header
    assert "Пробелы в доказательной базе" in note
    # Must NOT contain English sentinels
    assert "EVIDENCE_GAP" not in note
    assert "CRITICAL" not in note  # severity literal stays in metadata only
    # The note as a whole must produce zero language-lint warnings on
    # its own (the {/api/...} URL path is the only Latin allowed here,
    # and the lint regex strips URLs).
    warnings = lint_output_language(note)
    assert not warnings, (
        f"gap warning leaked Latin tokens to confidence_note: "
        f"{[w.token for w in warnings]!r}"
    )


@pytest.mark.asyncio
async def test_gap_count_by_severity_aggregation_in_metadata():
    """Mixed severities — counts in metadata match what's in the list.

    Sub-question topics chosen with disjoint vocabulary so the matcher
    doesn't accidentally cross-attach a single source to multiple
    sub_questions and shift the severity counts.
    """
    sub_qs = [
        _sq("sq1", "Какие риски ставки центрального банка?"),  # critical
        _sq("sq2", "Какие тренды цен квартир премиум-сегмента?"),  # moderate
        _sq("sq3", "Какова доля ипотечных сделок у населения?"),  # minor
        _sq("sq4", "Какие факторы выбора девелопера элитного сегмента?"),  # critical
    ]
    analysis = _analysis_with(
        # sq2 — moderate (matches цены/квартир/премиум via title, no auth)
        (
            "https://realty-blog.ru/trendy-cen-kvartir-premium",
            "Цены квартир премиум-сегмента 2024 — обзор",
        ),
        # sq3 — minor (one rosstat); vocab limited to ипотека/население
        # so it doesn't bleed into sq1/2/4
        (
            "https://rosstat.gov.ru/ipoteka-naselenie-2024.pdf",
            "Ипотечные сделки у населения 2024",
        ),
    )
    final = _empty_final()
    await _attach_evidence_gaps(final, sub_qs, analysis, emitter=_NullEmitter())

    counts = final.metadata["gap_count_by_severity"]
    assert counts == {"critical": 2, "moderate": 1, "minor": 1}
    # Sum equals list length
    assert sum(counts.values()) == len(final.metadata["evidence_gaps"])


# ---------------------------------------------------------------------------
# Confidence-note prefix preservation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_warning_prefixed_preserves_existing_confidence_note():
    """If LLM (or Step 1.2 LOW_EVIDENCE_QUALITY) already wrote a note,
    the gap warning must prefix it, not replace it.
    """
    sub_qs = [_sq("sq1", "Какие риски рынка жилья?")]
    analysis = _analysis_with()
    original = "⚠ Низкое качество источников: исходный текст из Step 1.2."
    final = _empty_final(confidence_note=original)
    await _attach_evidence_gaps(final, sub_qs, analysis, emitter=_NullEmitter())

    note = final.executive_summary.confidence_note
    assert note.startswith("⚠ Пробелы в доказательной базе")
    assert original in note  # original preserved at the bottom


@pytest.mark.asyncio
async def test_no_sub_questions_short_circuits_safely():
    """When the prompt-master path was 'none' or 'domain_template_ru_re'
    (no SubQuestion objects), the helper should still be safe to call.
    Caller-side guard already skips it, but the helper itself must not
    blow up if called with empty list.
    """
    final = _empty_final()
    await _attach_evidence_gaps(
        final, [], AnalysisOutput(), emitter=_NullEmitter()
    )
    assert final.metadata["evidence_gaps"] == []
    assert final.executive_summary.confidence_note == ""


# ---------------------------------------------------------------------------
# _format_gap_warning_for_confidence_note unit tests
# ---------------------------------------------------------------------------


def test_format_gap_warning_caps_long_lists_at_eight():
    """Visual cap: more than 8 gaps → truncate with "…и ещё N" footer
    so confidence_note doesn't grow unbounded.
    """
    gaps = [
        EvidenceGap(
            sub_question_id=f"sq{i}",
            sub_question_text=f"sub-question {i}",
            severity="critical",
            reason="test",
        )
        for i in range(12)
    ]
    text = _format_gap_warning_for_confidence_note(gaps)
    assert "и ещё 4 под-вопросов" in text


def test_format_gap_warning_truncates_long_sub_question_text():
    """Each bullet stays one line — long sub_question_text gets …-truncated."""
    long_text = "Какие именно " + "очень-длинная-фраза " * 30 + "проблема?"
    gaps = [
        EvidenceGap(
            sub_question_id="sq1",
            sub_question_text=long_text,
            severity="critical",
            reason="test",
        )
    ]
    text = _format_gap_warning_for_confidence_note(gaps)
    # Bullet line ends with ellipsis, original full text not present
    assert "…" in text
    assert long_text not in text


def test_format_gap_warning_empty_for_empty_list():
    assert _format_gap_warning_for_confidence_note([]) == ""
