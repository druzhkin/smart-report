"""Bibliography post-processor.

Scans all text fields in FinalReport for [REF:source_url] markers.
Builds sequential [1], [2], [3]... numbering in order of first appearance.
Replaces [REF:source_url] with [N] in text.
Generates FinalReport.bibliography list of NumberedSource.
Computes citation_coverage = (numeric_claims_with_ref / total_numeric_claims).
"""

from __future__ import annotations

import re
from typing import Any

from .models import FinalReport, NumberedSource, SourceRef

# Pattern: [REF:any_url_or_id] — greedy match for URL content
_RE_REF = re.compile(r"\[REF:([^\]]+)\]")

# Pattern to detect a numeric claim (contains a number + unit)
# Matches: 55%, 883 тыс., 1384 фактов, 2024, +12%, 3-5%, etc.
_RE_NUMERIC_CLAIM = re.compile(
    r"\b\d[\d\s,.]*(?:%|тыс|млн|млрд|руб|м²|кв\.?\s*м|лот|ДДУ|сделок|проект|лет|год|этаж|место)\b",
    re.IGNORECASE,
)


def generate_bibliography(report: FinalReport) -> tuple[FinalReport, float]:
    """Post-process FinalReport:

    1. Scan all text fields for [REF:url] markers.
    2. Assign sequential numbers [1], [2], ... in first-appearance order.
    3. Replace [REF:url] with [N] in all text fields.
    4. Build report.bibliography = list[NumberedSource].
    5. Compute citation_coverage = cited_numeric / total_numeric.
    6. Set report.source_count = len(bibliography).

    Returns (updated_report, coverage_pct).
    """
    # Collect all text fields
    text_fields = _collect_text_fields(report)

    # First pass: discover all [REF:url] markers in order of appearance
    url_order: list[str] = []  # ordered unique URLs
    url_to_number: dict[str, int] = {}

    for field_text in text_fields.values():
        for m in _RE_REF.finditer(field_text):
            url = m.group(1).strip()
            if url not in url_to_number:
                url_order.append(url)
                url_to_number[url] = len(url_order)

    # Build source registry from report.all_sources and report.bibliography (existing SourceRefs)
    url_to_sourceref = _build_source_registry(report)

    # Build NumberedSource list
    bibliography: list[NumberedSource] = []
    for url in url_order:
        number = url_to_number[url]
        # Get or create SourceRef
        if url in url_to_sourceref:
            source_ref = url_to_sourceref[url]
        else:
            # Create a minimal SourceRef from the URL alone
            source_ref = SourceRef(
                url=url,
                confidence="secondary",
                accessed_via="manual_upload",
            )
        ns = NumberedSource(
            number=number,
            source_ref=source_ref,
            cited_in_sections=[],  # will be populated in second pass
        )
        bibliography.append(ns)

    # Second pass: replace [REF:url] → [N] in all text fields
    # Also track which sections cite which sources
    updated_fields: dict[str, str] = {}
    section_citations: dict[str, list[str]] = {name: [] for name in text_fields}

    for field_name, field_text in text_fields.items():
        updated_text = _replace_refs(field_text, url_to_number, section_citations[field_name])
        updated_fields[field_name] = updated_text

    # Update section citations on NumberedSource objects
    url_sections: dict[str, list[str]] = {url: [] for url in url_order}
    for field_name, urls in section_citations.items():
        for url in urls:
            if url in url_sections and field_name not in url_sections[url]:
                url_sections[url].append(field_name)

    # Rebuild bibliography with section info
    bibliography_with_sections: list[NumberedSource] = []
    for ns in bibliography:
        url = ns.source_ref.url
        ns_updated = NumberedSource(
            number=ns.number,
            source_ref=ns.source_ref,
            cited_in_sections=url_sections.get(url, []),
        )
        bibliography_with_sections.append(ns_updated)

    # Compute citation_coverage
    coverage = _compute_citation_coverage(text_fields, updated_fields)

    # Apply all updates to report (Pydantic v2 allows direct field assignment)
    _apply_text_updates(report, updated_fields)
    report.bibliography = bibliography_with_sections
    report.citation_coverage = round(coverage, 4)
    report.source_count = len(bibliography_with_sections)

    return report, coverage


def _collect_text_fields(report: FinalReport) -> dict[str, str]:
    """Collect all text fields from FinalReport that can contain [REF:...] markers."""
    fields: dict[str, str] = {}

    # Top-level text fields
    if report.main_synthesis:
        fields["main_synthesis"] = report.main_synthesis
    if report.consensus_section:
        fields["consensus_section"] = report.consensus_section
    if report.conflicts_section:
        fields["conflicts_section"] = report.conflicts_section
    if report.gaps_filled_section:
        fields["gaps_filled_section"] = report.gaps_filled_section

    # Executive summary
    es = report.executive_summary
    if es.main_answer:
        fields["executive_summary.main_answer"] = es.main_answer
    for i, finding in enumerate(es.top_findings):
        fields[f"executive_summary.top_findings[{i}]"] = finding

    # QA section
    for i, qa in enumerate(report.qa_section):
        fields[f"qa_section[{i}].answer"] = qa.answer

    # Callouts
    for i, cb in enumerate(report.callouts):
        fields[f"callouts[{i}].body"] = cb.body

    # Tables — captions
    for i, tbl in enumerate(report.tables):
        if tbl.caption:
            fields[f"tables[{i}].caption"] = tbl.caption

    return fields


def _apply_text_updates(report: FinalReport, updated_fields: dict[str, str]) -> None:
    """Apply updated (post-replacement) text back to FinalReport fields."""
    if "main_synthesis" in updated_fields:
        report.main_synthesis = updated_fields["main_synthesis"]
    if "consensus_section" in updated_fields:
        report.consensus_section = updated_fields["consensus_section"]
    if "conflicts_section" in updated_fields:
        report.conflicts_section = updated_fields["conflicts_section"]
    if "gaps_filled_section" in updated_fields:
        report.gaps_filled_section = updated_fields["gaps_filled_section"]
    if "executive_summary.main_answer" in updated_fields:
        report.executive_summary.main_answer = updated_fields["executive_summary.main_answer"]

    for i, qa in enumerate(report.qa_section):
        key = f"qa_section[{i}].answer"
        if key in updated_fields:
            # QAItem is a Pydantic model; we need to update it differently
            # Since Pydantic v2 allows attribute assignment on non-frozen models:
            report.qa_section[i] = report.qa_section[i].model_copy(
                update={"answer": updated_fields[key]}
            )

    for i, cb in enumerate(report.callouts):
        key = f"callouts[{i}].body"
        if key in updated_fields:
            report.callouts[i] = report.callouts[i].model_copy(
                update={"body": updated_fields[key]}
            )

    for i, tbl in enumerate(report.tables):
        key = f"tables[{i}].caption"
        if key in updated_fields and tbl.caption is not None:
            report.tables[i] = report.tables[i].model_copy(
                update={"caption": updated_fields[key]}
            )


def _replace_refs(
    text: str, url_to_number: dict[str, int], section_urls: list[str]
) -> str:
    """Replace all [REF:url] with [N] in text; populate section_urls list."""
    def replacer(m: re.Match) -> str:
        url = m.group(1).strip()
        n = url_to_number.get(url)
        if n is not None:
            if url not in section_urls:
                section_urls.append(url)
            return f"[{n}]"
        return m.group(0)  # Leave unknown REF unchanged

    return _RE_REF.sub(replacer, text)


def _build_source_registry(report: FinalReport) -> dict[str, SourceRef]:
    """Build url -> SourceRef lookup from all known sources in the report."""
    registry: dict[str, SourceRef] = {}

    # From all_sources (Source objects — convert to SourceRef)
    for src in report.all_sources:
        if src.url and src.url not in registry:
            registry[src.url] = SourceRef(
                url=src.url,
                title=src.title or None,
                confidence="secondary",
                accessed_via="manual_upload",
            )

    # From existing bibliography (if any)
    for ns in report.bibliography:
        url = ns.source_ref.url
        if url and url not in registry:
            registry[url] = ns.source_ref

    return registry


def _compute_citation_coverage(
    original_fields: dict[str, str],
    updated_fields: dict[str, str],
) -> float:
    """Compute what fraction of numeric claims have at least one [N] citation.

    Strategy: scan the updated text (where [REF:x] → [N]) for numeric claim
    patterns. For each, check if there's a [N] citation within 300 chars after.
    """
    # Merge all text together for analysis
    original_text = " ".join(original_fields.values())
    updated_text = " ".join(updated_fields.values())

    # Count numeric claims in original (before replacement)
    numeric_matches = list(_RE_NUMERIC_CLAIM.finditer(original_text))
    total_numeric = len(numeric_matches)
    if total_numeric == 0:
        return 1.0  # no numeric claims → trivially covered

    # Check what fraction of numeric patterns in updated text have nearby [N]
    # Use a sliding window approach in the updated text
    cited_numeric = 0
    _RE_CITATION_NUM = re.compile(r"\[\d+\]")

    for m in _RE_NUMERIC_CLAIM.finditer(updated_text):
        end = m.end()
        # Look 300 chars forward for [N]
        window = updated_text[end : end + 300]
        if _RE_CITATION_NUM.search(window):
            cited_numeric += 1

    return cited_numeric / total_numeric
