"""Data audit — fact coverage verification.

Checks how many high_relevance_facts from AnalysisOutput appear in FinalReport.
Returns a CoverageReport with verdict and list of missing facts.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .models import AnalysisOutput, FinalReport, NumericFact

Verdict = Literal["excellent", "acceptable", "poor", "critical_failure"]


class CoverageReport(BaseModel):
    """Result of fact-coverage audit."""

    model_config = ConfigDict(extra="forbid")

    coverage_pct: float
    facts_in_final: int
    high_relevance_total: int
    missing_high_relevance_facts: list[NumericFact] = Field(default_factory=list)
    verdict: Verdict
    detail: str = ""


def audit_fact_coverage(
    analysis: AnalysisOutput,
    final_report: FinalReport,
) -> CoverageReport:
    """Check how many high_relevance_facts appear in FinalReport text.

    For each NumericFact in analysis.high_relevance_facts:
      - Search for fact.value AND (fact.metric OR fact.subject) in all text fields.
      - Mark as covered / missing.

    Returns CoverageReport with:
      coverage_pct = facts_in_final / high_relevance
      missing_high_relevance_facts: list[NumericFact]
      verdict: "excellent" (>85%) | "acceptable" (75-85%) | "poor" (60-75%) | "critical_failure" (<60%)
    """
    high_relevance = analysis.high_relevance_facts
    total = len(high_relevance)

    if total == 0:
        return CoverageReport(
            coverage_pct=1.0,
            facts_in_final=0,
            high_relevance_total=0,
            missing_high_relevance_facts=[],
            verdict="excellent",
            detail="No high_relevance_facts to check (intake may not have run).",
        )

    # Collect all searchable text from FinalReport
    searchable_text = _collect_all_text(final_report)

    covered: list[NumericFact] = []
    missing: list[NumericFact] = []

    for fact in high_relevance:
        if _fact_present_in_text(fact, searchable_text):
            covered.append(fact)
        else:
            missing.append(fact)

    facts_in_final = len(covered)
    coverage_pct = facts_in_final / total if total > 0 else 1.0

    verdict = _compute_verdict(coverage_pct)
    detail = (
        f"{facts_in_final}/{total} high-relevance facts found in final report "
        f"({coverage_pct:.1%}). Verdict: {verdict}."
    )

    return CoverageReport(
        coverage_pct=round(coverage_pct, 4),
        facts_in_final=facts_in_final,
        high_relevance_total=total,
        missing_high_relevance_facts=missing,
        verdict=verdict,
        detail=detail,
    )


def _collect_all_text(report: FinalReport) -> str:
    """Concatenate all searchable text fields from FinalReport."""
    parts: list[str] = []

    if report.main_synthesis:
        parts.append(report.main_synthesis)
    if report.consensus_section:
        parts.append(report.consensus_section)
    if report.conflicts_section:
        parts.append(report.conflicts_section)
    if report.gaps_filled_section:
        parts.append(report.gaps_filled_section)

    es = report.executive_summary
    if es.main_answer:
        parts.append(es.main_answer)
    parts.extend(es.top_findings)
    for kn in es.key_numbers:
        parts.append(f"{kn.value} {kn.metric} {kn.subject}")

    for qa in report.qa_section:
        parts.append(qa.answer)

    for cb in report.callouts:
        parts.append(cb.body)

    for tbl in report.tables:
        for row in tbl.rows:
            parts.append(" ".join(row))

    for knh in report.key_numbers_highlight:
        parts.append(f"{knh.value} {knh.label}")

    return "\n".join(parts)


def _fact_present_in_text(fact: NumericFact, text: str) -> bool:
    """Check if a numeric fact is represented in the given text.

    Strategy: look for fact.value (normalized) AND at least one of
    (fact.metric[:20], fact.subject[:20]) within 500 chars of each other.
    """
    # Normalize value for search — strip whitespace, normalize digits
    value_normalized = _normalize_for_search(fact.value)
    if not value_normalized:
        return False

    # Find all occurrences of the value in text
    try:
        pattern = re.compile(re.escape(value_normalized), re.IGNORECASE)
    except re.error:
        return False

    for m in pattern.finditer(text):
        # Look in surrounding window for metric or subject keywords
        start = max(0, m.start() - 300)
        end = min(len(text), m.end() + 300)
        window = text[start:end]

        # Check for metric keywords
        metric_words = _extract_keywords(fact.metric)
        subject_words = _extract_keywords(fact.subject)

        if any(_keyword_in_text(w, window) for w in metric_words):
            return True
        if any(_keyword_in_text(w, window) for w in subject_words):
            return True

    return False


def _normalize_for_search(value: str) -> str:
    """Normalize a numeric value for fuzzy search."""
    # Remove thousands separators, normalize spaces
    v = value.strip()
    # Remove trailing punctuation
    v = v.rstrip(".,;:")
    # Normalize non-breaking spaces
    v = v.replace("\u00a0", " ").replace("\u202f", " ")
    return v[:50]  # limit to avoid regex explosion


def _extract_keywords(text: str) -> list[str]:
    """Extract meaningful keywords from a metric or subject string."""
    # Split on whitespace and punctuation, filter short words
    words = re.split(r"[\s,/\-–—]+", text)
    # Keep words >= 4 chars that are likely meaningful
    return [w for w in words if len(w) >= 4]


def _keyword_in_text(keyword: str, text: str) -> bool:
    """Check if a keyword appears in text (case-insensitive)."""
    return keyword.lower() in text.lower()


def _compute_verdict(coverage_pct: float) -> Verdict:
    if coverage_pct > 0.85:
        return "excellent"
    if coverage_pct >= 0.75:
        return "acceptable"
    if coverage_pct >= 0.60:
        return "poor"
    return "critical_failure"


def build_retry_feedback(
    coverage_report: CoverageReport,
    max_facts_to_show: int = 50,
) -> str:
    """Build a feedback message for the Synthesizer retry.

    Lists missing facts so the Synthesizer can include them in the appendix.
    """
    missing = coverage_report.missing_high_relevance_facts[:max_facts_to_show]
    if not missing:
        return ""

    lines = [
        f"## Coverage audit feedback",
        f"Current coverage: {coverage_report.coverage_pct:.1%} — verdict: {coverage_report.verdict}",
        f"You missed {len(coverage_report.missing_high_relevance_facts)} high-relevance facts.",
        "",
        "Please include the following facts in your report. Add them to 'Дополнительные данные' appendix if they don't fit the main narrative. Each MUST have a [REF:url] citation.",
        "",
        "Missing facts:",
    ]
    for fact in missing:
        src_urls = [s.url for s in fact.sources if not s.url.startswith("opaque:")]
        src_str = f" [{src_urls[0]}]" if src_urls else " [no url]"
        lines.append(
            f"- {fact.value} {fact.metric} ({fact.subject}){src_str}"
        )

    if len(coverage_report.missing_high_relevance_facts) > max_facts_to_show:
        lines.append(
            f"... and {len(coverage_report.missing_high_relevance_facts) - max_facts_to_show} more."
        )

    return "\n".join(lines)
