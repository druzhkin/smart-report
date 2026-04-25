"""Evidence-grade tag parsing and variance checks (v4.5 Phase 1 Step 1.1).

The Synthesizer is instructed to prefix every material claim in its output
with one of four inline tags:

    [STRONG] [MODERATE] [WEAK] [SPECULATIVE]

This module is the source-of-truth for parsing those tags out of the
text fields of a FinalReport, and for the acceptance check that the
LLM is not assigning a uniform grade to everything.

The tags themselves live inline in plain text; we deliberately do NOT
add a structured field to the Pydantic schema — the synthesizer prompt
pins the placement, and post-processing extracts when needed. This
keeps the change non-breaking for downstream consumers (DOCX renderer,
language-lint, bibliography builder).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import FinalReport

EVIDENCE_GRADES: tuple[str, ...] = ("STRONG", "MODERATE", "WEAK", "SPECULATIVE")

_RE_GRADE = re.compile(r"\[(STRONG|MODERATE|WEAK|SPECULATIVE)\]")


def count_evidence_grades(text: str) -> dict[str, int]:
    """Return a count of each grade tag occurring in *text*.

    Always returns all four keys (zeros for absent grades) so callers
    can index without a KeyError. Order in the dict follows
    ``EVIDENCE_GRADES``.
    """
    counts: dict[str, int] = {grade: 0 for grade in EVIDENCE_GRADES}
    for match in _RE_GRADE.finditer(text):
        counts[match.group(1)] += 1
    return counts


def has_grade_variance(text: str, *, min_distinct: int = 2) -> bool:
    """Return True when *text* contains at least *min_distinct* different grades.

    Used by the acceptance test for Step 1.1: a synthesized report whose
    every claim is the same grade has either lost the grading instruction
    or is performing rote tagging — both of which defeat the purpose.

    Empty text and text with no grades return False (no variance to check).
    """
    counts = count_evidence_grades(text)
    distinct = sum(1 for c in counts.values() if c > 0)
    return distinct >= min_distinct


def evidence_grade_distribution(report: "FinalReport") -> dict[str, int]:
    """Sum grade tags across all user-visible text fields of *report*.

    Mirrors the field selection in ``synthesizer.full_report_text`` so the
    distribution reflects everything a reader would see, not just the
    main_synthesis body.
    """
    parts: list[str] = []

    if report.main_synthesis:
        parts.append(report.main_synthesis)
    if report.consensus_section:
        parts.append(report.consensus_section)
    if report.conflicts_section:
        parts.append(report.conflicts_section)
    if report.gaps_filled_section:
        parts.append(report.gaps_filled_section)

    parts.extend(report.executive_summary.top_findings)

    for item in report.qa_section:
        parts.append(item.answer)

    for callout in report.callouts:
        parts.append(callout.body)

    for knh in report.key_numbers_highlight:
        parts.append(knh.label)

    return count_evidence_grades("\n".join(parts))


def total_grades(distribution: dict[str, int]) -> int:
    """Sum of all grade occurrences in a distribution dict."""
    return sum(distribution.values())
