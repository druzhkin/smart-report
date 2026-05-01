"""Pre-render quality gate for premium publication storyboards."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .models import PremiumPage, PremiumReportDocument

FORBIDDEN_CLIENT_SURFACE_TERMS = (
    "Interpretation",
    "What it means",
    "RANKING BAR",
    "TIME SERIES",
    "EVIDENCE QUALITY",
    "SOURCE TABLE",
    "Source reliability mix",
    "risk-style exhibit",
    "Structured chart generated",
    "Use this exhibit",
    "\u041f\u043e\u0437\u0438\u0446\u0438\u044f \u0430\u0432\u0442\u043e\u0440\u0430",
)

DATA_VISUAL_TYPES = {
    "hero_kpi_strip",
    "ranking_bar",
    "time_series",
    "distribution",
    "scenario_matrix",
    "risk_heatmap",
    "evidence_quality",
    "waterfall",
    "market_map",
    "source_table",
}

SOURCE_REQUIRED_VISUAL_TYPES = DATA_VISUAL_TYPES - {"source_table"}

REQUIRED_EARLY_VISUAL_TYPES = {
    "hero_kpi_strip",
    "ranking_bar",
    "risk_heatmap",
    "evidence_quality",
}


def assess_premium_storyboard_quality(document: PremiumReportDocument) -> dict[str, Any]:
    """Assess authored storyboard quality before any renderer hides defects.

    Artifact QA catches geometry defects after rendering. This gate catches the
    editorial failure mode the user flagged: pages with only text, pages with
    only visuals, raw technical labels, and exhibits that are not source-backed.
    """

    pages = list(document.pages or [])
    issues: list[dict[str, str]] = []
    metrics = _storyboard_metrics(pages)

    if metrics["page_count"] < 8:
        issues.append(
            _issue(
                "storyboard_too_short",
                "critical",
                f"Storyboard has {metrics['page_count']} page(s); expected at least 8 authored pages.",
                "Add enough thesis, exhibit, decision, and appendix pages before rendering.",
            )
        )
    if metrics["visual_ratio"] < 0.65:
        issues.append(
            _issue(
                "storyboard_visual_ratio_low",
                "major",
                f"Only {metrics['visual_ratio']:.0%} of pages have a real visual.",
                "Add visuals to narrative pages or merge weak pages into stronger exhibit-led pages.",
            )
        )
    if metrics["early_visual_pages"] < 4:
        issues.append(
            _issue(
                "storyboard_not_visual_early",
                "major",
                f"Only {metrics['early_visual_pages']} of the first 6 authored pages are visual.",
                "Front-load executive KPI, chart, source-quality, and risk/scenario exhibits.",
            )
        )
    missing_early = REQUIRED_EARLY_VISUAL_TYPES - set(metrics["early_visual_types"])
    if missing_early:
        issues.append(
            _issue(
                "storyboard_missing_early_visual_types",
                "major",
                "Missing early visual type(s): " + ", ".join(sorted(missing_early)),
                "Ensure the first pages include KPI, ranking, risk/conflict, and evidence-quality visuals.",
            )
        )
    if metrics["source_backed_visual_ratio"] < 0.70:
        issues.append(
            _issue(
                "storyboard_visual_sources_weak",
                "major",
                f"Only {metrics['source_backed_visual_ratio']:.0%} of data visuals carry source notes.",
                "Attach source notes to chart, fact, evidence, and appendix visuals before export.",
            )
        )

    for index, page in enumerate(pages, start=1):
        _check_page(index, page, issues)

    critical = sum(1 for issue in issues if issue["severity"] == "critical")
    major = sum(1 for issue in issues if issue["severity"] == "major")
    minor = sum(1 for issue in issues if issue["severity"] == "minor")
    score = max(0, 100 - critical * 30 - major * 12 - minor * 4)
    return {
        "ready": critical == 0 and major == 0 and score >= 88,
        "score": score,
        "issues": issues,
        "metrics": metrics,
    }


def _storyboard_metrics(pages: list[PremiumPage]) -> dict[str, Any]:
    visual_pages = [page for page in pages if _is_real_visual(page)]
    data_visual_pages = [page for page in pages if _requires_source_notes(page)]
    source_backed_visual_pages = [page for page in data_visual_pages if _source_notes(page)]
    early_pages = pages[:6]
    early_visual_pages = [page for page in early_pages if _is_real_visual(page)]
    early_visual_types = sorted(
        {
            str(page.visual.visual_type)
            for page in early_visual_pages
            if page.visual and str(page.visual.visual_type) in DATA_VISUAL_TYPES
        }
    )
    return {
        "page_count": len(pages),
        "visual_pages": len(visual_pages),
        "visual_ratio": _ratio(len(visual_pages), len(pages)),
        "early_visual_pages": len(early_visual_pages),
        "early_visual_types": early_visual_types,
        "data_visual_pages": len(data_visual_pages),
        "source_backed_visual_pages": len(source_backed_visual_pages),
        "source_backed_visual_ratio": _ratio(
            len(source_backed_visual_pages),
            len(data_visual_pages),
        ),
    }


def _check_page(index: int, page: PremiumPage, issues: list[dict[str, str]]) -> None:
    if len(_plain(page.thesis)) < 12:
        issues.append(
            _issue(
                "storyboard_page_missing_thesis",
                "major",
                f"Page {index} has no usable thesis.",
                "Each page needs a client-facing thesis, not only a label.",
            )
        )
    if page.page_type != "appendix" and len(_plain(page.narrative)) < 60:
        issues.append(
            _issue(
                "storyboard_page_narrative_too_thin",
                "major",
                f"Page {index} narrative is too thin.",
                "Add interpretation text that explains the evidence and why it matters.",
            )
        )
    if page.page_type != "appendix" and len(_plain(page.implication)) < 45:
        issues.append(
            _issue(
                "storyboard_page_implication_too_thin",
                "major",
                f"Page {index} implication is too thin.",
                "Add a decision implication, risk signal, or next action for the reader.",
            )
        )
    if _requires_source_notes(page) and not _source_notes(page):
        issues.append(
            _issue(
                "storyboard_page_visual_without_source",
                "major",
                f"Page {index} has a data visual without source notes.",
                "Carry the source note from the chart, fact, or evidence block into the page.",
            )
        )
    page_text = "\n".join(_page_text_parts(page))
    for term in FORBIDDEN_CLIENT_SURFACE_TERMS:
        if term in page_text:
            issues.append(
                _issue(
                    "storyboard_client_surface_leak",
                    "minor",
                    f"Page {index} contains client-surface leak: {term}.",
                    "Replace internal or technical renderer labels with polished publication wording.",
                )
            )


def _is_real_visual(page: PremiumPage) -> bool:
    if not page.visual:
        return False
    visual_type = str(page.visual.visual_type)
    return visual_type not in {"none", "narrative_text"}


def _is_data_visual(page: PremiumPage) -> bool:
    if not page.visual:
        return False
    return str(page.visual.visual_type) in DATA_VISUAL_TYPES


def _requires_source_notes(page: PremiumPage) -> bool:
    if not page.visual:
        return False
    return str(page.visual.visual_type) in SOURCE_REQUIRED_VISUAL_TYPES


def _source_notes(page: PremiumPage) -> list[str]:
    notes = list(page.source_notes or [])
    if page.visual:
        notes.extend(page.visual.source_notes or [])
    return [note for note in notes if _plain(note)]


def _page_text_parts(page: PremiumPage) -> Iterable[str]:
    yield page.page_type
    yield page.thesis
    yield page.narrative
    yield page.implication
    if page.visual:
        yield page.visual.title
        yield from _walk_text(page.visual.data)
        yield from page.visual.source_notes
    yield from page.source_notes


def _walk_text(value: Any) -> Iterable[str]:
    if value is None:
        return
    if isinstance(value, str):
        yield value
        return
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key)
            yield from _walk_text(child)
        return
    if isinstance(value, (list, tuple, set)):
        for child in value:
            yield from _walk_text(child)
        return
    yield str(value)


def _plain(value: object) -> str:
    return " ".join(str(value or "").split())


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def _issue(code: str, severity: str, message: str, recommendation: str) -> dict[str, str]:
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "recommendation": recommendation,
    }
