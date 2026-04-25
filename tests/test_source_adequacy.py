"""Tests for v4.5 Phase 1 Step 1.2 — source-adequacy heuristic.

Covers:
  * is_authoritative_url — domain detection (case, subdomain, IDN, opaque)
  * count_authoritative_sources — heterogeneous iterables
  * assess_evidence_quality — boundary at min_authoritative
  * Integration with synthesizer._coerce_final_report — metadata
    mutation and confidence_note prefixing
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from smart_report.authoritative_sources import (
    AUTHORITATIVE_RU_RE_DOMAINS,
    assess_evidence_quality,
    count_authoritative_sources,
    is_authoritative_url,
)
from smart_report.models import (
    AnalysisOutput,
    Source,
    SourceRef,
    V4Session,
    UploadedMarkdown,
)
from smart_report.synthesizer import _coerce_final_report


# ---------------------------------------------------------------------------
# is_authoritative_url
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "https://rosstat.gov.ru/storage/mediabank/foo.pdf",
        "https://erzrf.ru/zhilyye-kompleksy/region-77",
        "https://www.cbr.ru/statistics/macro_itm/svs/key-indicators/",
        "https://дом.рф/analytics/",
        "https://dom.rf/analytics/",
        "https://stat.minstroyrf.gov.ru/path",          # subdomain
        "https://JLLrussia.com/Insights/2024",          # mixed case
        "https://knightfrank.ru/research",
        "https://nfgroup.ru/research",
    ],
)
def test_is_authoritative_url_known_domains(url: str):
    assert is_authoritative_url(url) is True, url


@pytest.mark.parametrize(
    "url",
    [
        "",
        "opaque:perplexity_dr_1",
        "https://t.me/some_channel",
        "https://vc.ru/some-blog",
        "https://example.com/random-blog",
        "https://avito.ru/listing/123",
        "https://realty.yandex.ru/offer",
        "https://habr.com/ru/article/123",
    ],
)
def test_is_authoritative_url_rejects_non_authoritative(url: str):
    assert is_authoritative_url(url) is False, url


def test_authoritative_set_has_no_uppercase_entries():
    """Lookup is case-insensitive via lower(); registry must be lowercase."""
    for d in AUTHORITATIVE_RU_RE_DOMAINS:
        assert d == d.lower(), f"{d!r} must be lowercase in registry"


# ---------------------------------------------------------------------------
# count_authoritative_sources
# ---------------------------------------------------------------------------


def _src(url: str) -> Source:
    return Source(title=url, url=url, tool="perplexity", reliability="medium")


def test_count_authoritative_sources_with_source_models():
    sources = [
        _src("https://rosstat.gov.ru/storage/foo.pdf"),
        _src("https://example.com/blog"),
        _src("https://erzrf.ru/region-77"),
    ]
    assert count_authoritative_sources(sources) == 2


def test_count_authoritative_sources_with_dicts():
    sources = [
        {"url": "https://cbr.ru/key-rate"},
        {"url": "https://random-blog.ru/post"},
        {"title": "no url here"},
    ]
    assert count_authoritative_sources(sources) == 1


def test_count_authoritative_sources_with_source_refs():
    sources = [
        SourceRef(url="https://дом.рф/analytics", confidence="primary"),
        SourceRef(url="https://example.com", confidence="secondary"),
    ]
    assert count_authoritative_sources(sources) == 1


def test_count_authoritative_sources_handles_empty_iterable():
    assert count_authoritative_sources([]) == 0


# ---------------------------------------------------------------------------
# assess_evidence_quality
# ---------------------------------------------------------------------------


def test_assess_low_quality_when_no_authoritative_sources():
    sources = [_src("https://random-blog.ru"), _src("https://vc.ru/post")]
    quality, warning = assess_evidence_quality(sources)
    assert quality == "LOW_EVIDENCE_QUALITY"
    assert "найдено 0 авторитетных" in warning
    assert "минимума 2" in warning


def test_assess_low_quality_when_one_authoritative_source():
    sources = [_src("https://rosstat.gov.ru/foo"), _src("https://random-blog.ru")]
    quality, warning = assess_evidence_quality(sources)
    assert quality == "LOW_EVIDENCE_QUALITY"
    assert "найдено 1 авторитетных" in warning


# ---------------------------------------------------------------------------
# Phase 3 Step 3.1 Task 1.2 — EN-EU regulatory tier (Run 1 finding 3)
# ---------------------------------------------------------------------------


def test_eu_regulatory_urls_now_authoritative():
    """europa.eu and friends must count as authoritative after Step 3.1."""
    eu_urls = [
        "https://climate.ec.europa.eu/news-other-reads/news/eu-sets-worlds-first-voluntary-standard-permanent-carbon-removals-2026-02-03_en",
        "https://europarl.europa.eu/RegData/etudes/STUD/2025/772474/ECTI_STU(2025)772474_EN.pdf",
        "https://cinea.ec.europa.eu/programmes/innovation-fund/calls-regular-grants_en",
        "https://eur-lex.europa.eu/eli/reg/2024/3012/oj",
        "https://eea.europa.eu/publications/eu-emissions-trading-system",
        "https://carbongap.org/eu-carbon-removal-funding/",
    ]
    for url in eu_urls:
        assert is_authoritative_url(url), f"{url} must be authoritative after Step 3.1"


def test_q3_eu_dac_no_longer_low_evidence():
    """Q3 fixture-shape: 4+ EU regulatory sources should clear the 2-source
    threshold, so the global LOW_EVIDENCE_QUALITY check returns OK.
    """
    sources = [
        _src("https://climate.ec.europa.eu/eu-action/eu-funding-climate-action/innovation-fund"),
        _src("https://europarl.europa.eu/thinktank/en/document/EPRS_BRI(2026)785709"),
        _src("https://cinea.ec.europa.eu/programmes/innovation-fund/calls-regular-grants_en"),
        _src("https://medium.com/@blogger/eu-dac-overview"),  # non-authoritative
    ]
    quality, warning = assess_evidence_quality(sources)
    assert quality == "OK"
    assert warning == ""


def test_ru_re_domains_still_authoritative():
    """Backwards compat: existing RU RE adequacy checks unchanged."""
    sources = [
        _src("https://rosstat.gov.ru/storage/foo.pdf"),
        _src("https://erzrf.ru/region-77"),
        _src("https://random-blog.ru/post"),
    ]
    quality, _ = assess_evidence_quality(sources)
    assert quality == "OK"  # 2 RU RE authoritative sources, threshold met


def test_eu_and_ru_re_authoritative_dont_double_count():
    """Sanity: a URL is either RU RE or EU; we don't accidentally count
    europa.eu twice or rosstat.gov.ru as both.
    """
    eu_only = [_src("https://europa.eu/policy/x")]
    ru_only = [_src("https://rosstat.gov.ru/foo")]
    assert count_authoritative_sources(eu_only) == 1
    assert count_authoritative_sources(ru_only) == 1


def test_warning_contains_zero_latin_tokens_to_avoid_lint_retry():
    """Regression: warning text must contain zero Latin-script tokens.

    Reasoning: every non-whitelisted Latin token adds a language-lint
    warning. The Track 3 retry threshold is >20 — fixtures may sit at
    the edge, and silently adding 2–3 anglicisms here can push a clean
    run into a paid retry (proven during Step 1.2 development by
    test_v4_full_cycle going from 0.36 to 0.48 RUB).

    Keep the visible warning in pure Cyrillic; reserve the
    "LOW_EVIDENCE_QUALITY" sentinel string for metadata only.
    """
    from smart_report.i18n import lint_output_language

    _, warning = assess_evidence_quality([_src("https://random-blog.ru")])
    warnings = lint_output_language(warning)
    assert not warnings, (
        f"Warning text triggered {len(warnings)} language-lint warnings: "
        f"{[w.token for w in warnings]!r}. Replace each Latin token with "
        "a Russian equivalent to avoid pushing reports past the >20 retry "
        "threshold."
    )


def test_assess_ok_when_two_authoritative_sources_present():
    sources = [
        _src("https://rosstat.gov.ru/foo"),
        _src("https://erzrf.ru/region"),
        _src("https://random-blog.ru"),
    ]
    quality, warning = assess_evidence_quality(sources)
    assert quality == "OK"
    assert warning == ""


def test_assess_threshold_is_configurable():
    sources = [
        _src("https://rosstat.gov.ru/foo"),
        _src("https://erzrf.ru/region"),
    ]
    quality_ok, _ = assess_evidence_quality(sources, min_authoritative=2)
    quality_low, _ = assess_evidence_quality(sources, min_authoritative=3)
    assert quality_ok == "OK"
    assert quality_low == "LOW_EVIDENCE_QUALITY"


# ---------------------------------------------------------------------------
# Integration with synthesizer._coerce_final_report
# ---------------------------------------------------------------------------


def _build_session() -> V4Session:
    return V4Session(
        session_id="adq-1",
        raw_question="Q",
        source_reports=[
            UploadedMarkdown(filename="r1.md", content="x", word_count=1)
        ],
        analysis=AnalysisOutput(),
        created_at=datetime.now(timezone.utc),
    )


def _synth_payload(*, sources: list[dict], confidence_note: str = "") -> dict:
    return {
        "session_id": "adq-1",
        "question": "Q",
        "executive_summary": {
            "main_answer": "ответ",
            "top_findings": ["f1"],
            "key_numbers": [],
            "confidence_note": confidence_note,
            "what_meta_adds": "",
        },
        "main_synthesis": "body",
        "all_sources": sources,
    }


def test_coerce_final_report_marks_low_evidence_quality():
    payload = _synth_payload(
        sources=[
            {"title": "A blog", "url": "https://random-blog.ru/post"},
            {"title": "Another", "url": "https://vc.ru/article"},
        ]
    )
    report = _coerce_final_report(payload, session=_build_session())
    assert report.metadata["evidence_quality"] == "LOW_EVIDENCE_QUALITY"
    assert "evidence_warning" in report.metadata
    # Warning is prefixed onto confidence_note so it appears in renderers.
    assert report.executive_summary.confidence_note.startswith(
        "⚠ Низкое качество источников"
    )


def test_coerce_final_report_preserves_existing_confidence_note_after_warning():
    original_note = "Доверие среднее: vendor-bias по премиальному срезу."
    payload = _synth_payload(
        sources=[{"url": "https://random-blog.ru/x"}],
        confidence_note=original_note,
    )
    report = _coerce_final_report(payload, session=_build_session())
    note = report.executive_summary.confidence_note
    assert note.startswith("⚠ Низкое качество источников")
    assert original_note in note  # original preserved after the warning


def test_coerce_final_report_marks_ok_quality_when_threshold_met():
    payload = _synth_payload(
        sources=[
            {"title": "Rosstat", "url": "https://rosstat.gov.ru/foo"},
            {"title": "ERZ", "url": "https://erzrf.ru/region"},
            {"title": "Blog", "url": "https://example.com/post"},
        ],
        confidence_note="Высокое доверие.",
    )
    report = _coerce_final_report(payload, session=_build_session())
    assert report.metadata["evidence_quality"] == "OK"
    assert "evidence_warning" not in report.metadata
    # confidence_note is left untouched when OK.
    assert report.executive_summary.confidence_note == "Высокое доверие."


def test_coerce_final_report_handles_no_sources():
    """When the LLM returns no all_sources, we still mark evidence_quality."""
    payload = _synth_payload(sources=[])
    report = _coerce_final_report(payload, session=_build_session())
    assert report.metadata["evidence_quality"] == "LOW_EVIDENCE_QUALITY"
    assert "найдено 0" in report.metadata["evidence_warning"]
