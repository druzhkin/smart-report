"""Quality grade — post-run signal of how trustworthy the report is.

Read-only. Computed on demand from `session.final_report` + `session.analysis`.
Returns a dict shape that the frontend can render as a small badge widget
next to the report card.

Inputs:
    session.final_report.all_sources : list[Source] (each has .reliability)
    session.analysis.consensus       : list of agreed-on claims
    session.analysis.conflicts       : list of contradictions
    session.analysis.gaps            : list of unfilled gaps
    session.analysis.unverified_numbers : list of orphan numerics

Heuristic (intentionally simple — explainable to the user):
    strong_share = high-reliability sources / total
    diversity    = unique domains in all_sources / total
    coverage     = consensus_count / (consensus + gaps + conflicts), clamped

Composite score = 0.5 * strong_share + 0.3 * diversity + 0.2 * coverage,
in [0, 1]. Bands: A ≥ 0.75, B ≥ 0.55, C otherwise.

The endpoint also returns the raw counts so the UI can show "3 STRONG · 4
MODERATE · 1 WEAK · 8 unique domains" without re-deriving them client-side.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional
from urllib.parse import urlparse


@dataclass
class QualityGrade:
    grade: str                           # "A" | "B" | "C" | "N/A"
    score: float                         # composite [0, 1]
    strong_count: int
    moderate_count: int
    weak_count: int
    unique_domains: int
    total_sources: int
    consensus_count: int
    conflict_count: int
    gap_count: int
    unverified_number_count: int
    summary: str                         # one-line human-readable

    def to_dict(self) -> dict:
        return asdict(self)


def _domain(url: str) -> str:
    if not url:
        return ""
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return ""
    if host.startswith("www."):
        host = host[4:]
    return host


def compute_quality_grade(session) -> QualityGrade:
    """Compute the grade for a session. Tolerates missing analysis/final.

    A session without `final_report` returns grade="N/A" — there's nothing
    to grade until synthesize has run.
    """
    final = getattr(session, "final_report", None)
    if final is None:
        return QualityGrade(
            grade="N/A", score=0.0,
            strong_count=0, moderate_count=0, weak_count=0,
            unique_domains=0, total_sources=0,
            consensus_count=0, conflict_count=0, gap_count=0,
            unverified_number_count=0,
            summary="Отчёт ещё не готов — сначала запустите синтез.",
        )

    sources = list(getattr(final, "all_sources", None) or [])
    total = len(sources)

    strong = sum(1 for s in sources if getattr(s, "reliability", None) == "high")
    weak = sum(1 for s in sources if getattr(s, "reliability", None) == "low")
    moderate = total - strong - weak

    domains = {_domain(getattr(s, "url", "")) for s in sources}
    domains.discard("")
    unique_domains = len(domains)

    analysis = getattr(session, "analysis", None)
    consensus_count = len(getattr(analysis, "consensus", None) or []) if analysis else 0
    conflict_count = len(getattr(analysis, "conflicts", None) or []) if analysis else 0
    gap_count = len(getattr(analysis, "gaps", None) or []) if analysis else 0
    unverified_number_count = (
        len(getattr(analysis, "unverified_numbers", None) or []) if analysis else 0
    )

    if total == 0:
        strong_share = 0.0
        diversity = 0.0
    else:
        strong_share = strong / total
        diversity = unique_domains / total

    cov_total = consensus_count + gap_count + conflict_count
    coverage = consensus_count / cov_total if cov_total > 0 else 1.0

    score = 0.5 * strong_share + 0.3 * diversity + 0.2 * coverage
    score = max(0.0, min(1.0, score))

    if total == 0:
        grade = "C"
        summary = "Источники не указаны — невозможно оценить."
    elif score >= 0.75:
        grade = "A"
        summary = (
            f"Сильная доказательная база: {strong}/{total} STRONG, "
            f"{unique_domains} уникальных доменов."
        )
    elif score >= 0.55:
        grade = "B"
        summary = (
            f"Достаточно: {strong}/{total} STRONG, {gap_count} пробелов, "
            f"{conflict_count} противоречий."
        )
    else:
        grade = "C"
        summary = (
            f"Слабая база: {strong}/{total} STRONG, {gap_count} пробелов. "
            "Рассмотрите дополнительный DR-прогон."
        )

    return QualityGrade(
        grade=grade,
        score=round(score, 3),
        strong_count=strong,
        moderate_count=moderate,
        weak_count=weak,
        unique_domains=unique_domains,
        total_sources=total,
        consensus_count=consensus_count,
        conflict_count=conflict_count,
        gap_count=gap_count,
        unverified_number_count=unverified_number_count,
        summary=summary,
    )
