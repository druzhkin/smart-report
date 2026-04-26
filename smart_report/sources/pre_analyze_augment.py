"""Feature-flagged pre-analyze augment (M1 D2 B2.1 of two-week brief).

The two-week brief §3 B2.1 specifies a feature-flag route in "the existing
pipeline at the search call site". v4.5 has NO auto-search call — its
cycle is generate_prompt → user uploads Perplexity markdowns → analyze →
synthesize (manual DR). The closest analog to the brief's intent is a
**pre-analyze augment**: when enabled, call Valyu before analyze, package
hits as an UploadedMarkdown, prepend to session.source_reports.

This pattern mirrors Day 4 `scripts/ab_run2.py` but goes through the
new SearchBackend Protocol (§5.6) instead of calling ValyuClient
directly. M2 will wire the same hook for medical/scientific/regulatory_eu
per brief §4 B4.1.

Env vars:
  SMART_REPORT_VALYU_ENABLE_DOMAINS  comma-separated list of domains
                                     where Valyu should fire (e.g.
                                     "financial_us,medical_clinical").
                                     Empty / unset → augment disabled.
  SMART_REPORT_VALYU_FORCE_DOMAIN    optional override; bypasses
                                     question-text domain detection.
                                     Required for queries that don't
                                     classify into a Valyu-covered domain
                                     by heuristics (e.g. Q1 EV is
                                     ru_automotive but the live smoke
                                     should target sec.gov via
                                     financial_us hint).

The brief's `ValyuPrimaryFailedError` fail-fast semantics: if
`SearchResult.is_empty_or_error` AND domain is in the enable list,
augment raises so the harness can bubble up the failure rather than
silently falling back to Perplexity-only.

Path note: per BLOCKERS.md A8, lives at `smart_report/sources/`.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from smart_report.domain_detector import QueryDomain, detect_query_domain
from smart_report.models import UploadedMarkdown
from smart_report.sources.base import SearchResult
from smart_report.sources.valyu_adapter import ValyuAdapter

_logger = logging.getLogger(__name__)


# Map our QueryDomain enum (Day 5 routing matrix labels) to the
# brief's domain identifiers used in the feature-flag env var.
# RU domains map to russian_market (Valyu doesn't cover) — those will
# never match the financial_us / medical_clinical / etc. enable list.
_QUERY_DOMAIN_TO_BRIEF_LABEL: dict[QueryDomain, str] = {
    QueryDomain.RU_REAL_ESTATE: "russian_market",
    QueryDomain.RU_AUTOMOTIVE: "russian_market",
    QueryDomain.RU_TECH_SAAS: "russian_market",
    QueryDomain.EU_REGULATORY: "regulatory_eu",
    QueryDomain.GLOBAL_TECH: "technical_research",
    QueryDomain.GENERIC: "general",
}


class ValyuPrimaryFailedError(RuntimeError):
    """Raised when Valyu was the primary route per feature flag and failed.

    Per two-week brief §3 B2.1: fail-fast on enabled-domain Valyu errors so
    the harness surfaces the failure rather than silent-degrading to
    Perplexity-only baseline.
    """


def enabled_domains_from_env() -> list[str]:
    raw = os.environ.get("SMART_REPORT_VALYU_ENABLE_DOMAINS", "").strip()
    if not raw:
        return []
    return [d.strip() for d in raw.split(",") if d.strip()]


def forced_domain_from_env() -> Optional[str]:
    """Optional override of question-text-derived domain detection."""
    raw = os.environ.get("SMART_REPORT_VALYU_FORCE_DOMAIN", "").strip()
    return raw or None


def domain_for_question(question: str) -> str:
    """Return the brief-style domain label for the question.

    Honours `SMART_REPORT_VALYU_FORCE_DOMAIN` override if set.
    """
    forced = forced_domain_from_env()
    if forced:
        return forced
    qd = detect_query_domain(question)
    return _QUERY_DOMAIN_TO_BRIEF_LABEL.get(qd, "general")


def _valyu_results_to_markdown(question: str, result: SearchResult, domain: str) -> str:
    """Adapt SearchResult to a Perplexity-style markdown the v4 intake can consume.

    Format mirrors Day 4 `valyu_results_to_markdown` (which existed before
    the SearchBackend Protocol abstraction) but pulls fields from the
    Protocol-shaped Source instead of raw ValyuResult.
    """
    lines = [
        f"# Valyu DeepSearch results — {question}",
        "",
        f"_Backend: valyu (domain hint: {domain})_",
        f"_Result count: {len(result.sources)}_",
        "",
    ]
    for i, src in enumerate(result.sources, 1):
        title = src.title or "(untitled)"
        lines.append(f"## [{i}] {title}")
        meta = src.raw_metadata or {}
        if meta.get("publication_date"):
            lines.append(f"_Published: {meta['publication_date']}_")
        if meta.get("valyu_source"):
            lines.append(f"_Dataset: {meta['valyu_source']}_")
        if meta.get("relevance_score") is not None:
            lines.append(f"_Relevance: {meta['relevance_score']:.2f}_")
        lines.append("")
        lines.append(src.snippet or "(no snippet)")
        lines.append("")
        lines.append(f"Citation: {src.url}")
        lines.append("")
    lines.append("## Sources")
    lines.append("")
    for i, src in enumerate(result.sources, 1):
        lines.append(f"{i}. {src.url}")
    return "\n".join(lines)


async def maybe_run_valyu_augment(
    question: str,
    *,
    valyu_adapter: Optional[ValyuAdapter] = None,
    max_results: int = 10,
) -> tuple[Optional[UploadedMarkdown], Optional[SearchResult], str]:
    """Per feature flag, run Valyu on the question and return an UploadedMarkdown.

    Returns ``(upload, result, domain)``:
      - upload: UploadedMarkdown to prepend to session.source_reports, or
        None if augment was skipped (flag off, domain not in enable list).
      - result: SearchResult from the Valyu call, or None if skipped.
      - domain: the resolved domain label (for telemetry/logging).

    Raises:
      ValyuPrimaryFailedError when augment fired but Valyu returned
      empty/error AND the resolved domain is in the enable list.
    """
    enabled = enabled_domains_from_env()
    domain = domain_for_question(question)

    if not enabled:
        _logger.info("valyu augment disabled (no env flag)")
        return (None, None, domain)

    if domain not in enabled:
        _logger.info(
            "valyu augment skipped: domain=%r not in enabled=%r",
            domain,
            enabled,
        )
        return (None, None, domain)

    adapter = valyu_adapter or ValyuAdapter()
    result = await adapter.search(
        question, domain_hint=domain, max_results=max_results
    )

    if result.is_empty_or_error:
        raise ValyuPrimaryFailedError(
            f"Valyu was primary for domain={domain!r} but returned "
            f"empty/error: {result.error or 'no results'}"
        )

    md = _valyu_results_to_markdown(question, result, domain)
    upload = UploadedMarkdown(
        filename=f"valyu_{domain}_augment.md",
        content=md,
        detected_tool="other",
        word_count=len(md.split()),
    )
    return (upload, result, domain)
