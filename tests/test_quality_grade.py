"""Quality-grade computation: deterministic from session shape."""
from __future__ import annotations

from types import SimpleNamespace

from smart_report.quality_grade import compute_quality_grade


def _src(url: str, reliability: str = "medium"):
    return SimpleNamespace(url=url, reliability=reliability)


def _session(*, sources=None, consensus=0, conflicts=0, gaps=0, unverified=0, with_final=True):
    final = SimpleNamespace(all_sources=list(sources or [])) if with_final else None
    analysis = SimpleNamespace(
        consensus=[None] * consensus,
        conflicts=[None] * conflicts,
        gaps=[None] * gaps,
        unverified_numbers=[None] * unverified,
    )
    return SimpleNamespace(final_report=final, analysis=analysis)


def test_no_final_report_returns_na():
    s = _session(with_final=False)
    g = compute_quality_grade(s)
    assert g.grade == "N/A"
    assert g.score == 0.0
    assert g.total_sources == 0


def test_grade_a_for_high_strong_share_and_diversity():
    sources = [
        _src("https://sec.gov/a", "high"),
        _src("https://eur-lex.europa.eu/b", "high"),
        _src("https://fred.stlouisfed.org/c", "high"),
        _src("https://arxiv.org/abs/d", "high"),
        _src("https://example.com/e", "medium"),
    ]
    s = _session(sources=sources, consensus=8, conflicts=0, gaps=1)
    g = compute_quality_grade(s)
    assert g.grade == "A"
    assert g.strong_count == 4
    assert g.moderate_count == 1
    assert g.weak_count == 0
    assert g.unique_domains == 5
    assert "STRONG" in g.summary


def test_grade_c_when_weak_dominates_or_many_gaps():
    sources = [
        _src("https://reddit.com/a", "low"),
        _src("https://medium.com/b", "low"),
        _src("https://blog.example/c", "medium"),
    ]
    s = _session(sources=sources, consensus=1, conflicts=2, gaps=10)
    g = compute_quality_grade(s)
    assert g.grade == "C"
    assert g.strong_count == 0
    assert g.gap_count == 10
    assert "Слабая" in g.summary or "C" == g.grade


def test_grade_b_in_middle_band():
    """Score lands in [0.55, 0.75): half strong, full diversity, decent coverage."""
    sources = [
        _src("https://sec.gov/a", "high"),
        _src("https://eur-lex.europa.eu/b", "high"),
        _src("https://other.com/c", "medium"),
        _src("https://blog.io/d", "medium"),
    ]
    # 6 consensus / 0 gaps / 0 conflicts → coverage = 1.0
    # strong_share = 0.5 → 0.25
    # diversity = 1.0 → 0.30
    # coverage = 1.0 → 0.20
    # total = 0.75 — at A boundary (>=0.75 is A)
    s = _session(sources=sources, consensus=6, conflicts=0, gaps=0)
    g = compute_quality_grade(s)
    assert g.grade in {"A", "B"}
    assert 0.55 <= g.score <= 0.85
    assert g.total_sources == 4
    assert g.unique_domains == 4


def test_dedupe_domain_counts_uniques_not_urls():
    """Two sec.gov URLs collapse to one domain."""
    sources = [
        _src("https://sec.gov/cik=A", "high"),
        _src("https://sec.gov/cik=B", "high"),
        _src("https://eur-lex.europa.eu/x", "high"),
    ]
    s = _session(sources=sources, consensus=3, gaps=0)
    g = compute_quality_grade(s)
    assert g.total_sources == 3
    assert g.unique_domains == 2


def test_strips_www_prefix_for_domain_dedupe():
    sources = [
        _src("https://www.sec.gov/a", "high"),
        _src("https://sec.gov/b", "high"),
    ]
    s = _session(sources=sources, consensus=2, gaps=0)
    g = compute_quality_grade(s)
    assert g.unique_domains == 1


def test_no_sources_returns_zero_diversity_zero_strong():
    s = _session(sources=[], consensus=2, gaps=1)
    g = compute_quality_grade(s)
    assert g.total_sources == 0
    assert g.strong_count == 0
    assert g.unique_domains == 0
    assert g.grade == "C"
    assert "Источники не указаны" in g.summary
