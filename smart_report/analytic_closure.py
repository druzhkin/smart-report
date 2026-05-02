"""Closure scoring for analytic-depth follow-up research.

The analytic-depth layer can create research leads. This module checks whether
the follow-up material appears to close those leads. It is deliberately
heuristic and transparent: it scores coverage signals instead of claiming that
the answer is objectively true.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .analytic_depth import AnalyticDepthPlan, ResearchLead
from .models import UploadedMarkdown

ClosureStatus = Literal["closed", "partial", "not_closed", "not_started"]


class _ClosureBase(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class LeadClosure(_ClosureBase):
    lead_id: str
    kind: str
    priority: str
    status: ClosureStatus
    score: int
    matched_reports: list[str] = Field(default_factory=list)
    evidence_signals: list[str] = Field(default_factory=list)
    missing_signals: list[str] = Field(default_factory=list)
    recommendation: str = ""


class AnalyticClosureReport(_ClosureBase):
    overall_score: int
    closed: int
    partial: int
    not_closed: int
    not_started: int
    lead_count: int
    followup_report_count: int
    lead_closures: list[LeadClosure]
    summary: str


def assess_analytic_closure(
    depth_plan: AnalyticDepthPlan,
    followup_reports: list[UploadedMarkdown],
) -> AnalyticClosureReport:
    """Assess whether follow-up reports close analytic-depth research leads."""

    closures = [
        _score_lead(lead, followup_reports)
        for lead in depth_plan.research_leads
        if lead.priority in {"must", "should"}
    ]
    counts = Counter(item.status for item in closures)
    weighted = _weighted_score(closures)
    return AnalyticClosureReport(
        overall_score=weighted,
        closed=counts["closed"],
        partial=counts["partial"],
        not_closed=counts["not_closed"],
        not_started=counts["not_started"],
        lead_count=len(closures),
        followup_report_count=len(followup_reports),
        lead_closures=closures,
        summary=_summary(weighted, counts, len(closures), len(followup_reports)),
    )


def _score_lead(lead: ResearchLead, reports: list[UploadedMarkdown]) -> LeadClosure:
    if not reports:
        return LeadClosure(
            lead_id=lead.id,
            kind=lead.kind,
            priority=lead.priority,
            status="not_started",
            score=0,
            missing_signals=["No follow-up reports are attached to the session."],
            recommendation="Run the analytic-depth lead or upload a follow-up report.",
        )

    keywords = _lead_keywords(lead)
    candidates = [_report_signals(report, keywords, lead) for report in reports]
    matched = [item for item in candidates if item["matched"]]
    if not matched:
        return LeadClosure(
            lead_id=lead.id,
            kind=lead.kind,
            priority=lead.priority,
            status="not_started",
            score=0,
            missing_signals=["No follow-up report appears to address this lead."],
            recommendation="Run a targeted follow-up query for this lead.",
        )

    best = max(matched, key=lambda item: item["score"])
    score = min(100, int(best["score"]))
    status: ClosureStatus
    if score >= 70:
        status = "closed"
    elif score >= 40:
        status = "partial"
    else:
        status = "not_closed"

    missing = []
    if not best["has_url"]:
        missing.append("No URL/source citation found in the matched follow-up.")
    if not best["has_number"]:
        missing.append("No numeric evidence found in the matched follow-up.")
    if best["keyword_hits"] < 3:
        missing.append("Matched report has weak topical overlap with the lead.")
    if not best["has_adjudication_language"] and lead.kind == "resolve_conflict":
        missing.append("Conflict lead lacks explicit adjudication language.")
    if lead.id == "required_source_families":
        missing_families = _missing_required_families(lead, best)
        if missing_families:
            missing.append(
                "Required source families still missing: " + ", ".join(missing_families) + "."
            )
            score = min(score, 65 if best["required_family_hits"] else 35)
            status = "partial" if score >= 40 else "not_closed"

    return LeadClosure(
        lead_id=lead.id,
        kind=lead.kind,
        priority=lead.priority,
        status=status,
        score=score,
        matched_reports=[str(best["filename"])],
        evidence_signals=list(best["signals"]),
        missing_signals=missing,
        recommendation=_recommendation(status, lead.kind),
    )


def _report_signals(report: UploadedMarkdown, keywords: set[str], lead: ResearchLead) -> dict:
    text = report.content or ""
    lowered = text.lower()
    lead_marker = f"smart report analytic-depth lead: {lead.id.lower()}"
    has_lead_marker = lead_marker in lowered
    keyword_hits = sum(1 for keyword in keywords if keyword in lowered)
    has_url = bool(re.search(r"https?://", text))
    has_number = bool(re.search(r"\d+(?:[.,]\d+)?\s?(?:%|pp|p\.p\.|rub|usd|eur|mln|bn|trn)?", lowered))
    has_source_language = any(token in lowered for token in ("source", "url", "report", "data", "according"))
    has_candidate_source = any(src.lower() in lowered for src in lead.candidate_sources if src)
    required_family_hits = _required_family_hits(lowered, lead)
    has_adjudication_language = any(
        token in lowered
        for token in ("therefore", "stronger", "weaker", "contradict", "resolved", "scope", "definition")
    )
    matched = has_lead_marker or keyword_hits >= 2 or has_candidate_source
    score = 0
    signals = []
    if matched:
        score += 15
        signals.append(f"topical_overlap:{keyword_hits}")
    if has_lead_marker:
        score += 25
        signals.append("analytic_depth_lead_marker")
    if keyword_hits >= 3:
        score += 20
    if has_url:
        score += 20
        signals.append("url_citation")
    if has_number:
        score += 15
        signals.append("numeric_evidence")
    if has_source_language:
        score += 10
        signals.append("source_language")
    if has_candidate_source:
        score += 20
        signals.append("candidate_source_match")
    if required_family_hits:
        score += min(25, 5 * len(required_family_hits))
        signals.append(f"required_source_family_hits:{len(required_family_hits)}")
    if lead.kind == "resolve_conflict" and has_adjudication_language:
        score += 20
        signals.append("adjudication_language")
    if lead.kind == "verify_number" and has_number and has_url:
        score += 10
        signals.append("number_with_source")
    return {
        "filename": report.filename,
        "matched": matched,
        "score": score,
        "signals": signals,
        "keyword_hits": keyword_hits,
        "has_url": has_url,
        "has_number": has_number,
        "has_adjudication_language": has_adjudication_language,
        "has_lead_marker": has_lead_marker,
        "required_family_hits": required_family_hits,
    }


def _required_family_hits(text: str, lead: ResearchLead) -> set[str]:
    if lead.id != "required_source_families":
        return set()
    hits: set[str] = set()
    for family in lead.target_entities:
        family_l = family.lower()
        markers = _SOURCE_FAMILY_MARKERS.get(family_l, (family_l,))
        if any(marker.lower() in text for marker in markers):
            hits.add(family_l)
    return hits


def _missing_required_families(lead: ResearchLead, signal: dict) -> list[str]:
    if lead.id != "required_source_families":
        return []
    hits = set(signal.get("required_family_hits") or set())
    return [family for family in lead.target_entities if family.lower() not in hits]


def _lead_keywords(lead: ResearchLead) -> set[str]:
    text = " ".join(
        [
            lead.id,
            lead.kind,
            lead.prompt,
            lead.rationale,
            " ".join(lead.target_entities),
            " ".join(lead.target_metrics),
            " ".join(lead.linked_to),
        ]
    )
    words = {
        word.lower()
        for word in re.findall(r"[A-Za-zА-Яа-я0-9][A-Za-zА-Яа-я0-9_.-]{3,}", text)
        if word.lower() not in _STOP_WORDS
    }
    return set(list(words)[:40])


def _weighted_score(closures: list[LeadClosure]) -> int:
    if not closures:
        return 0
    weights = {"must": 1.6, "should": 1.0, "could": 0.5}
    total_weight = sum(weights.get(item.priority, 1.0) for item in closures)
    if total_weight <= 0:
        return 0
    return round(
        sum(item.score * weights.get(item.priority, 1.0) for item in closures)
        / total_weight
    )


def _summary(score: int, counts: Counter, lead_count: int, followup_count: int) -> str:
    if lead_count == 0:
        return "No analytic-depth leads were available for closure scoring."
    if followup_count == 0:
        return "No follow-up reports have been uploaded; analytic-depth leads remain open."
    return (
        f"Closure score {score}/100 across {lead_count} priority leads: "
        f"{counts['closed']} closed, {counts['partial']} partial, "
        f"{counts['not_closed']} not closed, {counts['not_started']} not started."
    )


def _recommendation(status: ClosureStatus, kind: str) -> str:
    if status == "closed":
        return "Use the follow-up evidence in the final synthesis and data pack."
    if status == "partial":
        return "Run one narrower follow-up focused on missing URLs, numbers, or adjudication."
    if kind == "resolve_conflict":
        return "Ask for primary-source adjudication of the conflicting claims."
    if kind == "verify_number":
        return "Ask for original source, exact date, unit, definition, and contradiction check."
    return "Run a targeted follow-up and require source URLs plus numeric evidence."


_STOP_WORDS = {
    "this",
    "that",
    "with",
    "from",
    "into",
    "which",
    "what",
    "find",
    "source",
    "sources",
    "return",
    "exact",
    "numbers",
    "dates",
    "urls",
    "claim",
    "evidence",
    "report",
    "market",
}


_SOURCE_FAMILY_MARKERS = {
    "cbr": ("cbr.ru", "bank of russia", "central bank", "банк россии", "цб"),
    "domrf": ("dom.rf", "дом.рф", "xn--d1aqf.xn--p1ai"),
    "rosstat": ("rosstat.gov.ru", "rosstat", "росстат"),
    "erz": ("erzrf.ru", "erz", "ерз"),
    "mos": ("mos.ru", "stroi.mos.ru", "стройкомплекс"),
    "europa": ("europa.eu",),
    "commission": ("ec.europa.eu", "european commission"),
    "parliament": ("europarl.europa.eu", "european parliament"),
    "legal_text": ("eur-lex.europa.eu", "eur-lex"),
    "minpromtorg": ("minpromtorg.gov.ru", "минпромторг"),
    "autostat": ("autostat.ru", "автостат"),
    "aeb": ("aebrus.ru",),
    "academic": ("arxiv.org", "pubmed", "doi", "journal", "semanticscholar"),
    "vendor_docs": ("docs.", "documentation", "github.com"),
    "benchmark": ("benchmark", "dataset", "mckinsey", "bcg", "gartner", "forrester"),
    "github": ("github.com",),
    "company": ("annual report", "investor relations", "official company"),
    "market": ("industry association", "market research"),
    "regulatory": ("regulator", "government", ".gov"),
    "primary": ("official statistics", "regulatory", "company filing", ".gov", ".edu"),
    "industry": ("industry association", "agency report"),
}
