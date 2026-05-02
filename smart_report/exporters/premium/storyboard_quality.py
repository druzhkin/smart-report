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

PLACEHOLDER_CLIENT_CONTENT = (
    "example.com",
    "internal QA fixture",
    "stub source",
    "demo evidence",
    "placeholder",
    "Synthetic fixture",
    "Forecast a market with scenario and risk recommendations",
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
        "remediation_plan": _remediation_plan(issues, metrics),
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
    placeholder_pages = [
        index
        for index, page in enumerate(pages, start=1)
        if _placeholder_hits("\n".join(_page_text_parts(page)))
    ]
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
        "placeholder_pages": placeholder_pages,
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
    placeholder_hits = _placeholder_hits(page_text)
    if placeholder_hits:
        issues.append(
            _issue(
                "storyboard_placeholder_content",
                "critical",
                f"Page {index} contains placeholder/demo content: "
                + ", ".join(placeholder_hits[:5]),
                "Replace demo prompts, fake URLs, and synthetic fixture labels with client evidence.",
            )
        )
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


def _placeholder_hits(text: str) -> list[str]:
    lowered = text.lower()
    return sorted(
        {
            pattern
            for pattern in PLACEHOLDER_CLIENT_CONTENT
            if pattern.lower() in lowered
        }
    )


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


def _remediation_plan(
    issues: list[dict[str, str]],
    metrics: dict[str, Any],
) -> list[dict[str, Any]]:
    """Translate storyboard defects into executable editorial work items."""

    if not issues:
        return []

    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for issue in issues:
        code = issue["code"]
        if code in seen:
            continue
        seen.add(code)
        spec = _remediation_for_issue(code, issue, metrics)
        items.append({**spec, "issue_code": code, "severity": issue["severity"]})

    severity_rank = {"critical": 0, "major": 1, "minor": 2}
    items.sort(key=lambda item: (severity_rank.get(str(item["severity"]), 3), item["priority"]))
    return items


def _remediation_for_issue(
    code: str,
    issue: dict[str, str],
    metrics: dict[str, Any],
) -> dict[str, Any]:
    fallback = {
        "priority": 90,
        "action": issue.get("recommendation") or issue["message"],
        "target": "storyboard",
        "artifact": "editorial_revision",
        "acceptance_criteria": [issue["message"]],
    }
    plans: dict[str, dict[str, Any]] = {
        "storyboard_placeholder_content": {
            "priority": 5,
            "action": "Replace demo prompts, fake URLs, and synthetic fixture labels with real client evidence and publication-safe wording.",
            "target": "source_integrity",
            "artifact": "client_ready_storyboard",
            "acceptance_criteria": ["placeholder_pages == []"],
            "current_value": metrics.get("placeholder_pages"),
            "target_value": [],
        },
        "storyboard_too_short": {
            "priority": 10,
            "action": "Добавить авторские страницы, чтобы в отчете было не менее 8 содержательных страниц.",
            "target": "report_outline",
            "artifact": "narrative_pages",
            "acceptance_criteria": [
                "page_count >= 8",
                "каждая новая страница содержит тезис, текст, вывод и источники для визуалов",
            ],
            "current_value": metrics.get("page_count"),
            "target_value": 8,
        },
        "storyboard_visual_ratio_low": {
            "priority": 20,
            "action": "Добавить или объединить страницы так, чтобы минимум 65% страниц содержали содержательные визуалы.",
            "target": "visual_storyboard",
            "artifact": "charts_or_kpi_blocks",
            "acceptance_criteria": ["visual_ratio >= 0.65"],
            "current_value": metrics.get("visual_ratio"),
            "target_value": 0.65,
        },
        "storyboard_not_visual_early": {
            "priority": 25,
            "action": "Перенести KPI, ранжирование, риски и качество источников в первые шесть страниц.",
            "target": "executive_sequence",
            "artifact": "front_loaded_exhibits",
            "acceptance_criteria": ["early_visual_pages >= 4"],
            "current_value": metrics.get("early_visual_pages"),
            "target_value": 4,
        },
        "storyboard_missing_early_visual_types": {
            "priority": 30,
            "action": "Добавить недостающие ранние визуалы: KPI, ранжирование, риск/конфликт и качество источников.",
            "target": "executive_sequence",
            "artifact": "required_exhibit_mix",
            "acceptance_criteria": [
                "early_visual_types includes hero_kpi_strip",
                "early_visual_types includes ranking_bar",
                "early_visual_types includes risk_heatmap",
                "early_visual_types includes evidence_quality",
            ],
            "current_value": metrics.get("early_visual_types"),
        },
        "storyboard_visual_sources_weak": {
            "priority": 35,
            "action": "Добавить подписи источников ко всем визуалам, которые используются как доказательства.",
            "target": "visual_source_notes",
            "artifact": "source_backed_exhibits",
            "acceptance_criteria": ["source_backed_visual_ratio >= 0.70"],
            "current_value": metrics.get("source_backed_visual_ratio"),
            "target_value": 0.70,
        },
        "storyboard_page_missing_thesis": {
            "priority": 40,
            "action": "Написать клиентский тезис для каждой страницы, где сейчас есть только заголовок.",
            "target": "page_thesis",
            "artifact": "client_thesis",
            "acceptance_criteria": ["each non-appendix page thesis has at least 12 visible characters"],
        },
        "storyboard_page_narrative_too_thin": {
            "priority": 45,
            "action": "Расширить тонкие текстовые страницы: добавить интерпретацию фактов и объяснение, почему это важно.",
            "target": "page_narrative",
            "artifact": "analytical_text",
            "acceptance_criteria": ["each non-appendix page narrative has at least 60 visible characters"],
        },
        "storyboard_page_implication_too_thin": {
            "priority": 50,
            "action": "Добавить к тонким страницам управленческий вывод, риск-сигнал или следующий шаг.",
            "target": "page_implication",
            "artifact": "decision_implication",
            "acceptance_criteria": ["each non-appendix page implication has at least 45 visible characters"],
        },
        "storyboard_page_visual_without_source": {
            "priority": 55,
            "action": "Перенести источники из графика, факта или evidence-блока в подпись визуала.",
            "target": "page_source_notes",
            "artifact": "visual_citation_notes",
            "acceptance_criteria": ["all data visuals have source_notes"],
        },
        "storyboard_client_surface_leak": {
            "priority": 70,
            "action": "Заменить внутренние технические подписи на аккуратные формулировки для публикации.",
            "target": "client_language",
            "artifact": "language_cleanup",
            "acceptance_criteria": ["no forbidden client-surface terms remain"],
        },
    }
    return plans.get(code, fallback)
