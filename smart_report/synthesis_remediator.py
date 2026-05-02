"""Deterministic remediation for weak synthesized reports.

The LLM owns the analytical storyline. This module owns product safety: when
the LLM returns a thin FinalReport, use already-collected analysis/source data
to add minimum client-facing structure instead of shipping a blank-looking
report.
"""

from __future__ import annotations

import re
from typing import Iterable

from .models import (
    AnalysisOutput,
    CalloutBlock,
    ChartSpec,
    FinalReport,
    KeyNumberHighlight,
    NumericFact,
    Source,
    Table,
)


def remediate_final_report(
    report: FinalReport,
    *,
    analysis: AnalysisOutput | None = None,
) -> FinalReport:
    """Return a report with minimum narrative, citations, and visual support.

    The function is conservative: it only uses facts, consensus/conflict/gap
    summaries, and source URLs already present in the session. It does not
    invent outside data or new sources.
    """

    source_url = _best_source_url(report.all_sources)
    report.executive_summary.top_findings = [
        _ensure_ref(item, source_url) for item in report.executive_summary.top_findings
    ]
    report.executive_summary.main_answer = _ensure_ref(
        report.executive_summary.main_answer, source_url
    )

    if len(report.main_synthesis) < 5000:
        report.main_synthesis = _expand_main_synthesis(
            report,
            analysis=analysis,
            source_url=source_url,
        )
    if len(report.tables) < 3:
        report.tables = _merge_tables(
            report.tables,
            _fallback_tables(report, analysis=analysis, source_url=source_url),
            limit=4,
        )
    if len(report.charts) < 3:
        report.charts = _merge_charts(
            report.charts,
            _fallback_charts(report, analysis=analysis, source_url=source_url),
            limit=4,
        )
    if len(report.key_numbers_highlight) < 3:
        report.key_numbers_highlight = _merge_key_numbers(
            report.key_numbers_highlight,
            _fallback_key_numbers(report, analysis=analysis, source_url=source_url),
            limit=6,
        )
    if len(report.callouts) < 3:
        report.callouts = _merge_callouts(
            report.callouts,
            _fallback_callouts(report, analysis=analysis, source_url=source_url),
            limit=5,
        )

    report.metadata["synthesis_remediation_applied"] = True
    report.metadata["synthesis_remediation"] = {
        "main_synthesis_chars": len(report.main_synthesis),
        "tables": len(report.tables),
        "charts": len(report.charts),
        "callouts": len(report.callouts),
        "key_numbers_highlight": len(report.key_numbers_highlight),
    }
    return report


def _expand_main_synthesis(
    report: FinalReport,
    *,
    analysis: AnalysisOutput | None,
    source_url: str,
) -> str:
    existing = report.main_synthesis.strip()
    sections: list[str] = []
    if existing:
        sections.append(existing)
    sections.append(
        "## Executive interpretation\n\n"
        + _ensure_ref(report.executive_summary.main_answer or report.question, source_url)
    )
    if report.executive_summary.top_findings:
        findings = "\n".join(
            f"- {_ensure_ref(item, source_url)}"
            for item in report.executive_summary.top_findings[:6]
        )
        sections.append("## Key findings\n\n" + findings)

    if analysis is not None and analysis.consensus:
        rows = [
            _ensure_ref(
                f"{item.claim} Confidence: {item.confidence}. Supporting sources: "
                f"{', '.join(item.supporting_sources[:4]) or source_url}.",
                source_url,
            )
            for item in analysis.consensus[:6]
        ]
        sections.append("## Where the evidence agrees\n\n" + "\n\n".join(rows))
    elif report.consensus_section:
        sections.append("## Where the evidence agrees\n\n" + _ensure_ref(report.consensus_section, source_url))

    if analysis is not None and analysis.conflicts:
        rows = [
            _ensure_ref(
                f"{item.topic}: {item.source_a} says {item.claim_a}; "
                f"{item.source_b} says {item.claim_b}. Resolution: {item.resolution_hint}.",
                source_url,
            )
            for item in analysis.conflicts[:6]
        ]
        sections.append("## Open contradictions and resolution logic\n\n" + "\n\n".join(rows))
    elif report.conflicts_section:
        sections.append("## Open contradictions and resolution logic\n\n" + _ensure_ref(report.conflicts_section, source_url))

    facts = _top_numeric_facts(analysis, limit=12)
    if facts:
        fact_lines = [
            _ensure_ref(
                f"{fact.value} {fact.metric} for {fact.subject}"
                + (f" in {fact.timeframe}" if fact.timeframe else "")
                + f". Relevance: {fact.relevance_to_question}.",
                _fact_source_url(fact) or source_url,
            )
            for fact in facts
        ]
        sections.append("## Quantitative evidence base\n\n" + "\n".join(f"- {line}" for line in fact_lines))

    if analysis is not None and analysis.gaps:
        gap_lines = [
            _ensure_ref(
                f"{gap.topic}: {gap.why_critical} Required evidence: {gap.what_to_find}.",
                source_url,
            )
            for gap in analysis.gaps[:5]
        ]
        sections.append("## Remaining evidence gaps\n\n" + "\n".join(f"- {line}" for line in gap_lines))
    elif report.gaps_filled_section:
        sections.append("## Remaining evidence gaps\n\n" + _ensure_ref(report.gaps_filled_section, source_url))

    sections.append(
        "## Implications for the client\n\n"
        + _ensure_ref(
            "The decision should be made on the intersection of quantified facts, "
            "source reliability, and unresolved uncertainty. The report should not "
            "treat a single provider's estimate as final when conflicts or evidence "
            "gaps remain visible.",
            source_url,
        )
    )
    return "\n\n".join(section for section in sections if section.strip())


def _fallback_tables(
    report: FinalReport,
    *,
    analysis: AnalysisOutput | None,
    source_url: str,
) -> list[Table]:
    tables: list[Table] = []
    if report.all_sources:
        tables.append(
            Table(
                title="Source reliability matrix",
                columns=["Source", "Reliability", "Tool", "Use in report"],
                rows=[
                    [
                        source.title or source.url,
                        source.reliability,
                        source.tool or "unspecified",
                        "Evidence base",
                    ]
                    for source in report.all_sources[:10]
                ],
                caption=_ensure_ref("Shows which sources anchor the client-facing conclusions.", source_url),
                source_ref=source_url,
            )
        )
    facts = _top_numeric_facts(analysis, limit=8)
    if facts:
        tables.append(
            Table(
                title="Key numeric facts",
                columns=["Value", "Metric", "Subject", "Timeframe", "Source"],
                rows=[
                    [
                        fact.value,
                        fact.metric,
                        fact.subject,
                        fact.timeframe or "",
                        _fact_source_url(fact) or source_url,
                    ]
                    for fact in facts
                ],
                caption=_ensure_ref("Consolidates the numeric facts used in the analytical narrative.", source_url),
                source_ref=source_url,
            )
        )
    if analysis is not None and analysis.conflicts:
        tables.append(
            Table(
                title="Contradiction register",
                columns=["Topic", "Source A", "Claim A", "Source B", "Claim B", "Resolution"],
                rows=[
                    [
                        item.topic,
                        item.source_a,
                        item.claim_a,
                        item.source_b,
                        item.claim_b,
                        item.resolution_hint,
                    ]
                    for item in analysis.conflicts[:8]
                ],
                caption=_ensure_ref("Separates conflicting evidence before the report takes a position.", source_url),
                source_ref=source_url,
            )
        )
    if analysis is not None and analysis.gaps:
        tables.append(
            Table(
                title="Evidence gap register",
                columns=["Gap", "Why it matters", "What to find", "Candidate sources"],
                rows=[
                    [
                        item.topic,
                        item.why_critical,
                        item.what_to_find,
                        ", ".join(item.candidate_sources[:4]),
                    ]
                    for item in analysis.gaps[:8]
                ],
                caption=_ensure_ref("Makes limitations explicit instead of hiding them in prose.", source_url),
                source_ref=source_url,
            )
        )
    return tables


def _fallback_charts(
    report: FinalReport,
    *,
    analysis: AnalysisOutput | None,
    source_url: str,
) -> list[ChartSpec]:
    charts: list[ChartSpec] = []
    reliability_counts: dict[str, int] = {}
    for source in report.all_sources:
        reliability_counts[source.reliability] = reliability_counts.get(source.reliability, 0) + 1
    if reliability_counts:
        charts.append(
            ChartSpec(
                chart_type="bar",
                title="Source reliability mix",
                data={
                    "labels": list(reliability_counts.keys()),
                    "values": list(reliability_counts.values()),
                    "source_ref": source_url,
                },
                x_label="Reliability",
                y_label="Source count",
                caption=_ensure_ref("Shows whether the evidence base is dominated by high-quality sources.", source_url),
            )
        )
    facts = _top_numeric_facts(analysis, limit=6)
    if facts:
        charts.append(
            ChartSpec(
                chart_type="bar",
                title="Top numeric evidence points",
                data={
                    "labels": [fact.subject[:40] or fact.metric for fact in facts],
                    "values": [_numeric_value(fact.value) for fact in facts],
                    "source_ref": source_url,
                },
                x_label="Subject",
                y_label="Extracted value",
                caption=_ensure_ref("Ranks the numeric facts available for synthesis.", source_url),
            )
        )
    if analysis is not None:
        charts.append(
            ChartSpec(
                chart_type="bar",
                title="Analytical workload by issue type",
                data={
                    "labels": ["consensus", "conflicts", "gaps", "unverified"],
                    "values": [
                        len(analysis.consensus),
                        len(analysis.conflicts),
                        len(analysis.gaps),
                        len(analysis.unverified_numbers),
                    ],
                    "source_ref": source_url,
                },
                x_label="Issue type",
                y_label="Count",
                caption=_ensure_ref("Shows whether the report is driven by agreement, conflict, or missing evidence.", source_url),
            )
        )
    return charts


def _fallback_key_numbers(
    report: FinalReport,
    *,
    analysis: AnalysisOutput | None,
    source_url: str,
) -> list[KeyNumberHighlight]:
    items: list[KeyNumberHighlight] = []
    for number in report.executive_summary.key_numbers[:6]:
        items.append(
            KeyNumberHighlight(
                value=number.value,
                label=_ensure_ref(f"{number.metric} {number.subject}".strip(), number.source_url or source_url),
                source_ref=number.source_url or source_url,
                importance="primary",
            )
        )
    for fact in _top_numeric_facts(analysis, limit=max(0, 6 - len(items))):
        items.append(
            KeyNumberHighlight(
                value=fact.value,
                label=_ensure_ref(f"{fact.metric} for {fact.subject}".strip(), _fact_source_url(fact) or source_url),
                source_ref=_fact_source_url(fact) or source_url,
                importance="primary",
            )
        )
    if not items and report.all_sources:
        items.append(
            KeyNumberHighlight(
                value=str(len(report.all_sources)),
                label=_ensure_ref("sources in evidence base", source_url),
                source_ref=source_url,
                importance="secondary",
            )
        )
    return items


def _fallback_callouts(
    report: FinalReport,
    *,
    analysis: AnalysisOutput | None,
    source_url: str,
) -> list[CalloutBlock]:
    callouts = [
        CalloutBlock(
            kind="insight",
            title="Decision anchor",
            body=_ensure_ref(report.executive_summary.main_answer or report.question, source_url),
        )
    ]
    if analysis is not None and analysis.conflicts:
        callouts.append(
            CalloutBlock(
                kind="warning",
                title="Evidence conflict",
                body=_ensure_ref(
                    f"{len(analysis.conflicts)} material conflict(s) remain and should be resolved before treating the estimate as final.",
                    source_url,
                ),
            )
        )
    if analysis is not None and analysis.gaps:
        callouts.append(
            CalloutBlock(
                kind="note",
                title="Known limitation",
                body=_ensure_ref(
                    f"{len(analysis.gaps)} evidence gap(s) remain; the report should state them explicitly.",
                    source_url,
                ),
            )
        )
    if report.all_sources:
        callouts.append(
            CalloutBlock(
                kind="key_number",
                title="Evidence base",
                body=_ensure_ref(f"{len(report.all_sources)} sources support this synthesis.", source_url),
            )
        )
    return callouts


def _top_numeric_facts(analysis: AnalysisOutput | None, *, limit: int) -> list[NumericFact]:
    if analysis is None:
        return []
    facts = list(analysis.high_relevance_facts or [])
    if not facts:
        facts = [
            fact
            for fact in analysis.all_numeric_facts
            if fact.relevance_to_question in {"high", "medium"}
        ]
    return facts[:limit]


def _fact_source_url(fact: NumericFact) -> str:
    for source in fact.sources:
        if source.url:
            return source.url
    return ""


def _best_source_url(sources: Iterable[Source]) -> str:
    sources = list(sources)
    for reliability in ("high", "medium", "low"):
        for source in sources:
            if source.reliability == reliability and source.url:
                return source.url
    return sources[0].url if sources and sources[0].url else ""


def _ensure_ref(text: str, source_url: str) -> str:
    text = " ".join(str(text or "").split())
    if not text or not source_url:
        return text
    lowered = text.lower()
    if "[ref:" in lowered or source_url.lower() in lowered:
        return text
    return f"{text} [REF:{source_url}]"


def _numeric_value(value: str) -> float:
    match = re.search(r"-?\d+(?:[.,]\d+)?", str(value or "").replace(" ", ""))
    if not match:
        return 0.0
    return float(match.group(0).replace(",", "."))


def _merge_tables(current: list[Table], fallback: list[Table], *, limit: int) -> list[Table]:
    seen = {item.title for item in current}
    merged = list(current)
    for item in fallback:
        if item.title not in seen:
            merged.append(item)
            seen.add(item.title)
        if len(merged) >= limit:
            break
    return merged


def _merge_charts(current: list[ChartSpec], fallback: list[ChartSpec], *, limit: int) -> list[ChartSpec]:
    seen = {item.title for item in current}
    merged = list(current)
    for item in fallback:
        if item.title not in seen:
            merged.append(item)
            seen.add(item.title)
        if len(merged) >= limit:
            break
    return merged


def _merge_key_numbers(
    current: list[KeyNumberHighlight],
    fallback: list[KeyNumberHighlight],
    *,
    limit: int,
) -> list[KeyNumberHighlight]:
    seen = {item.label for item in current}
    merged = list(current)
    for item in fallback:
        if item.label not in seen:
            merged.append(item)
            seen.add(item.label)
        if len(merged) >= limit:
            break
    return merged


def _merge_callouts(
    current: list[CalloutBlock],
    fallback: list[CalloutBlock],
    *,
    limit: int,
) -> list[CalloutBlock]:
    seen = {item.title for item in current}
    merged = list(current)
    for item in fallback:
        if item.title not in seen:
            merged.append(item)
            seen.add(item.title)
        if len(merged) >= limit:
            break
    return merged
