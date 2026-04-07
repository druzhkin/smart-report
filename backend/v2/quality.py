from __future__ import annotations

import re
from statistics import fmean

from backend.schemas.report_schema import ReportOutput
from backend.v2.grounding import extract_numeric_facts, find_unsupported_precise_numbers
from backend.v2.models import (
    ClaimRecord,
    CoverageReport,
    CritiqueFinding,
    DecisionTrigger,
    EvidenceRecord,
    QualityAssessment,
    QualityDimensionScore,
    QualityIteration,
    ResearchQuestion,
    SourceLedgerEntry,
    SourceType,
    TaskSpec,
)


_STRONG_SOURCE_TYPES = {
    SourceType.OFFICIAL_DOCUMENTATION,
    SourceType.VENDOR_PAGE,
    SourceType.GOVERNMENT,
    SourceType.RESEARCH_PAPER,
    SourceType.BENCHMARK,
}

_NONTRIVIAL_MARKERS = (
    "vs",
    "versus",
    "relative",
    "compared",
    "outperform",
    "underperform",
    "tradeoff",
    "better",
    "worse",
    "stronger",
    "weaker",
    "because",
    "depends",
    "unless",
    "if ",
    "when ",
    "alternative",
    "counter",
    "lock-in",
    "latency",
    "cost",
    "reliability",
    "traceability",
    "governance",
    "risk",
    "switch",
    "эконом",
    "стоим",
    "риск",
    "сильн",
    "слаб",
    "лучше",
    "хуже",
    "альтернатив",
    "контрарг",
    "завис",
    "услов",
)

_TRADEOFF_MARKERS = (
    "tradeoff",
    "trade-off",
    "better",
    "worse",
    "stronger",
    "weaker",
    "cost",
    "latency",
    "reliability",
    "lock-in",
    "operating model",
    "failure mode",
    "switch",
    "эконом",
    "стоим",
    "надеж",
    "риск",
    "лучше",
    "хуже",
    "сильн",
    "слаб",
)

_ROADMAP_MARKERS = (
    "phase 1",
    "phase 2",
    "phase 3",
    "next 30 days",
    "next 90 days",
    "pilot",
    "rollout",
    "phase",
    "roadmap",
    "wave 1",
    "этап 1",
    "этап 2",
    "этап 3",
    "пилот",
    "внедр",
    "дорожн",
)

_OPTION_MARKERS = (
    "option space",
    "alternative",
    "comparator",
    "competitive set",
    "vs",
    "versus",
    "пространство альтернатив",
    "альтернатив",
    "сравнен",
)

_UNKNOWN_MARKERS = (
    "unknown",
    "still need validation",
    "open question",
    "uncertainty",
    "unknowns",
    "неизвест",
    "нужно проверить",
    "открыт",
    "неопредел",
)

_COUNTERARGUMENT_MARKERS = (
    "counterargument",
    "anti-thesis",
    "objection",
    "wrong choice",
    "materially weaker",
    "контрарг",
    "возраж",
    "неправиль",
    "слабее",
)

_HIDDEN_VARIABLE_MARKERS = (
    "hidden variable",
    "hidden variables",
    "lock-in",
    "latency",
    "operating burden",
    "operating model",
    "governance",
    "compliance",
    "скрыт",
    "операцион",
    "нагруз",
    "governance",
    "комплаенс",
)

_SWITCH_MARKERS = (
    "what could change the recommendation",
    "switch condition",
    "switch conditions",
    "decision trigger",
    "decision triggers",
    "boundary condition",
    "boundary conditions",
    "could change the recommendation",
    "может изменить рекомендацию",
    "триггер",
    "услов",
    "границ",
)

_ACTIONABLE_REVISION_DIMENSIONS = {
    "topic_alignment",
    "claim_depth",
    "evidence_density",
    "grounding_discipline",
    "lateral_breadth",
    "decision_usefulness",
    "presentation_depth",
}

_TOPIC_STOPWORDS = {
    "about",
    "across",
    "after",
    "against",
    "analysis",
    "analyze",
    "architecture",
    "boundaries",
    "build",
    "buy",
    "candidate",
    "candidates",
    "choose",
    "compare",
    "decision",
    "default",
    "design",
    "evidence",
    "explicit",
    "first",
    "grade",
    "iteration",
    "next",
    "product",
    "products",
    "quality",
    "question",
    "questions",
    "real",
    "recommend",
    "recommendation",
    "report",
    "should",
    "stack",
    "stacks",
    "support",
    "system",
    "systems",
    "that",
    "this",
    "traceability",
    "using",
    "what",
    "which",
    "with",
}


def _clamp(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    return max(lower, min(upper, value))


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    lowered = _normalize(text)
    return any(marker in lowered for marker in markers)


def _topic_tokens(*texts: str) -> set[str]:
    tokens: set[str] = set()
    for text in texts:
        normalized = re.sub(r"[_./:-]+", " ", str(text or "").lower())
        for token in re.findall(r"[a-zа-я0-9+]{3,}", normalized):
            if token.isdigit() or token in _TOPIC_STOPWORDS:
                continue
            tokens.add(token)
    return tokens


def _source_topic_alignment(entry: SourceLedgerEntry, topic_tokens: set[str]) -> float:
    if not topic_tokens:
        return 0.0
    haystack = re.sub(r"[_./:-]+", " ", f"{entry.title} {entry.domain} {entry.url}".lower())
    matched = sum(1 for token in topic_tokens if token in haystack)
    return min(1.0, matched / 3.0)


def _section_text(report: ReportOutput) -> str:
    parts = [report.executive_summary]
    parts.extend(section.content for section in report.sections)
    return "\n".join(parts)


def _extract_recommendation_bullets(report: ReportOutput) -> list[str]:
    bullets: list[str] = []
    for section in report.sections:
        if "recommend" in _normalize(section.title) or "рекомен" in _normalize(section.title):
            for line in section.content.splitlines():
                stripped = line.strip()
                if stripped.startswith("- "):
                    bullets.append(stripped)
    return bullets


def _word_count(report: ReportOutput) -> int:
    return sum(len(_normalize(part).split()) for part in [report.executive_summary, *[section.content for section in report.sections]])


def _meaningful_sentences(text: str) -> list[str]:
    return [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", text)
        if len(_normalize(sentence).split()) >= 10
    ]


def _table_count(report: ReportOutput) -> int:
    return len(re.findall(r"(?im)^\*{0,2}(?:exhibit\s+\d+|таблица\s+\d+)\*{0,2}(?::)?", _section_text(report)))


def _nontrivial_claim_count(claims: list[ClaimRecord]) -> int:
    total = 0
    for claim in claims:
        statement = _normalize(claim.statement)
        if len(statement) < 70:
            continue
        if any(marker in statement for marker in _NONTRIVIAL_MARKERS) or re.search(r"\d", statement):
            total += 1
    return total


def _score_word_range(word_count: int, target_low: int = 4500, target_high: int = 6500) -> float:
    if word_count < 1800:
        return 20.0
    if word_count < target_low:
        return _clamp(20.0 + (word_count - 1800) / max(1, target_low - 1800) * 80.0)
    if word_count <= target_high:
        return 100.0
    if word_count <= 8000:
        return _clamp(100.0 - (word_count - target_high) / max(1, 8000 - target_high) * 15.0)
    return 85.0


def _report_nontrivial_ratio(text: str) -> float:
    sentences = _meaningful_sentences(text)
    if not sentences:
        return 0.0
    analytical = [
        sentence
        for sentence in sentences
        if _contains_any(sentence, _NONTRIVIAL_MARKERS) or re.search(r"\d", sentence)
    ]
    return len(analytical) / len(sentences)


def _evidence_reference_count(text: str) -> int:
    return text.lower().count("[evidence:") + len(re.findall(r"\[[^\]]+\]\(https?://[^)]+\)", text))


def _section_title_matches(report: ReportOutput, markers: tuple[str, ...]) -> bool:
    return any(_contains_any(section.title, markers) for section in report.sections)


def _dimension_score(
    dimension: str,
    score: float,
    rationale: str,
    raw_metrics: dict[str, float | int | str],
) -> QualityDimensionScore:
    return QualityDimensionScore(
        dimension=dimension,
        score=round(_clamp(score), 2),
        rationale=rationale,
        raw_metrics=raw_metrics,
    )


def assess_report_quality(
    task_spec: TaskSpec,
    report: ReportOutput,
    source_ledger: list[SourceLedgerEntry],
    claims: list[ClaimRecord],
    evidence: list[EvidenceRecord],
    coverage: CoverageReport,
    adjacent_questions: list[ResearchQuestion],
    critique_findings: list[CritiqueFinding],
    decision_triggers: list[DecisionTrigger],
) -> QualityAssessment:
    source_count = len(source_ledger)
    topic_tokens = _topic_tokens(
        task_spec.request_spec.original_query,
        task_spec.request_spec.subject,
        task_spec.request_spec.decision_context,
        *task_spec.must_cover_questions[:4],
    )
    unique_domains = len({entry.domain for entry in source_ledger if entry.domain})
    unique_source_types = len({entry.source_type for entry in source_ledger})
    average_reliability = fmean([entry.reliability_score for entry in source_ledger]) if source_ledger else 0.0
    strong_source_ratio = (
        len([entry for entry in source_ledger if entry.source_type in _STRONG_SOURCE_TYPES]) / source_count
        if source_count
        else 0.0
    )
    source_alignment_ratio = (
        fmean([_source_topic_alignment(entry, topic_tokens) for entry in source_ledger])
        if source_ledger
        else 0.0
    )
    meaningful_sentences = _meaningful_sentences(_section_text(report))
    aligned_sentences = [
        sentence for sentence in meaningful_sentences if any(token in _normalize(sentence) for token in topic_tokens)
    ]
    report_alignment_ratio = len(aligned_sentences) / max(1, len(meaningful_sentences)) if topic_tokens else 1.0
    source_authority_score = 100.0 * (0.7 * average_reliability + 0.3 * strong_source_ratio)
    topic_alignment_score = 100.0 * (
        0.75 * source_alignment_ratio
        + 0.25 * report_alignment_ratio
    )

    source_diversity_score = 100.0 * (
        0.45 * min(1.0, unique_domains / 8.0)
        + 0.25 * min(1.0, unique_source_types / 5.0)
        + 0.30 * min(1.0, source_count / 10.0)
    )

    coverage_score = (
        100.0
        * (
            0.75 * coverage.coverage_ratio
            + 0.15 * coverage.strong_source_ratio
            + 0.10 * min(1.0, source_count / max(1, coverage.total_questions * 2))
        )
        - coverage.contradiction_count * 8.0
    )

    nontrivial_claims = _nontrivial_claim_count(claims)
    nontrivial_ratio = nontrivial_claims / max(1, len(claims))
    multi_source_claim_ratio = len([claim for claim in claims if len(claim.source_ids) >= 2]) / max(1, len(claims))
    recommendation_safe_ratio = len([claim for claim in claims if claim.recommendation_safe]) / max(1, len(claims))
    claim_depth_score = 100.0 * (
        0.25 * nontrivial_ratio
        + 0.15 * min(1.0, len(claims) / 28.0)
        + 0.15 * multi_source_claim_ratio
        + 0.10 * recommendation_safe_ratio
        + 0.35 * min(1.0, _report_nontrivial_ratio(_section_text(report)) / 0.42)
    )

    full_text = _section_text(report)
    evidence_reference_count = _evidence_reference_count(full_text)
    evidence_density_score = 100.0 * (
        0.35 * min(1.0, len(evidence) / max(1, coverage.total_questions * 5))
        + 0.25 * min(1.0, len(evidence) / max(1, len(claims) * 1.35))
        + 0.40 * min(1.0, evidence_reference_count / max(6.0, _word_count(report) / 550.0))
    )
    report_numeric_facts = extract_numeric_facts(full_text)
    grounded_numeric_facts = [
        fact for fact in report_numeric_facts
        if fact.family in {"money", "ratio", "latency", "context_window", "throughput", "benchmark"}
    ]
    unsupported_numbers = find_unsupported_precise_numbers(full_text, [claim.statement for claim in claims])
    grounded_numeric_ratio = (
        max(0.0, (len(grounded_numeric_facts) - len(unsupported_numbers)) / max(1, len(grounded_numeric_facts)))
        if grounded_numeric_facts
        else 1.0
    )
    grounding_score = 100.0 * (
        0.75 * grounded_numeric_ratio
        + 0.25 * min(1.0, len([claim for claim in claims if extract_numeric_facts(claim.statement)]) / max(1, len(grounded_numeric_facts)))
    )

    unique_adjacent_kinds = len({question.kind for question in adjacent_questions})
    has_counterargument_language = _contains_any(full_text, _COUNTERARGUMENT_MARKERS)
    has_hidden_variable_language = _contains_any(full_text, _HIDDEN_VARIABLE_MARKERS)
    has_switch_language = _contains_any(full_text, _SWITCH_MARKERS)
    lateral_breadth_score = 100.0 * (
        0.20 * min(1.0, len(adjacent_questions) / 5.0)
        + 0.12 * min(1.0, unique_adjacent_kinds / 4.0)
        + 0.12 * min(1.0, len(critique_findings) / 5.0)
        + 0.12 * min(1.0, len(decision_triggers) / 4.0)
        + 0.14 * (1.0 if _contains_any(full_text, _OPTION_MARKERS) or _section_title_matches(report, _OPTION_MARKERS) else 0.0)
        + 0.12 * (1.0 if has_counterargument_language else 0.0)
        + 0.08 * (1.0 if has_hidden_variable_language else 0.0)
        + 0.10 * (1.0 if has_switch_language else 0.0)
    )

    recommendation_bullets = _extract_recommendation_bullets(report)
    evidence_linked_bullets = len(
        [
            bullet
            for bullet in recommendation_bullets
            if "[evidence:" in bullet.lower() or re.search(r"\[[^\]]+\]\(https?://[^)]+\)", bullet)
        ]
    )
    has_tradeoff_language = _contains_any(full_text, _TRADEOFF_MARKERS)
    has_option_space = _contains_any(full_text, _OPTION_MARKERS)
    has_unknowns = _contains_any(full_text, _UNKNOWN_MARKERS)
    has_roadmap = _contains_any(full_text, _ROADMAP_MARKERS)
    decision_usefulness_score = 100.0 * (
        0.20 * min(1.0, len(recommendation_bullets) / 5.0)
        + 0.20 * min(1.0, evidence_linked_bullets / 5.0)
        + 0.20 * (1.0 if has_tradeoff_language else 0.0)
        + 0.20 * (1.0 if has_option_space else 0.0)
        + 0.10 * (1.0 if has_unknowns else 0.0)
        + 0.10 * (1.0 if has_roadmap else 0.0)
    )

    word_count = _word_count(report)
    exhibit_count = _table_count(report)
    section_count = len(report.sections)
    average_section_words = word_count / max(1, section_count)
    presentation_score = 100.0 * (
        0.35 * (_score_word_range(word_count) / 100.0)
        + 0.20 * min(1.0, section_count / 11.0)
        + 0.25 * min(1.0, exhibit_count / 6.0)
        + 0.20 * min(1.0, average_section_words / 320.0)
    )

    overclaim_penalty = _clamp(
        max(0.0, (0.7 - coverage.coverage_ratio) * 14.0)
        + coverage.contradiction_count * 5.0
        + max(0.0, (0.55 - source_alignment_ratio) * 18.0)
        + max(0.0, (0.45 - recommendation_safe_ratio) * 12.0)
        + len(unsupported_numbers) * 4.0,
        upper=20.0,
    )

    dimensions = [
        _dimension_score(
            "topic_alignment",
            topic_alignment_score,
            "Decision-grade reports should stay tightly anchored to the user's actual topic, not drift into adjacent but irrelevant literature.",
            {
                "topic_token_count": len(topic_tokens),
                "source_alignment_ratio": round(source_alignment_ratio, 3),
                "report_alignment_ratio": round(report_alignment_ratio, 3),
            },
        ),
        _dimension_score(
            "source_authority",
            source_authority_score,
            "High-value reports rely on reputable and directly attributable sources.",
            {
                "average_reliability": round(average_reliability, 3),
                "strong_source_ratio": round(strong_source_ratio, 3),
            },
        ),
        _dimension_score(
            "source_diversity",
            source_diversity_score,
            "A serious report should triangulate across domains and source types rather than echo one lane.",
            {
                "source_count": source_count,
                "unique_domains": unique_domains,
                "unique_source_types": unique_source_types,
            },
        ),
        _dimension_score(
            "coverage",
            coverage_score,
            "Core decision questions must be covered with enough evidence to support the recommendation.",
            {
                "covered_questions": coverage.covered_questions,
                "total_questions": coverage.total_questions,
                "coverage_ratio": round(coverage.coverage_ratio, 3),
                "contradiction_count": coverage.contradiction_count,
            },
        ),
        _dimension_score(
            "claim_depth",
            claim_depth_score,
            "Decision-grade analysis needs numerous non-trivial claims with comparisons, conditions, and tradeoffs.",
            {
                "claim_count": len(claims),
                "nontrivial_claim_count": nontrivial_claims,
                "nontrivial_ratio": round(nontrivial_ratio, 3),
                "multi_source_claim_ratio": round(multi_source_claim_ratio, 3),
                "report_nontrivial_ratio": round(_report_nontrivial_ratio(full_text), 3),
            },
        ),
        _dimension_score(
            "evidence_density",
            evidence_density_score,
            "Claims should rest on a dense evidence base, not isolated one-off observations.",
            {
                "evidence_count": len(evidence),
                "claim_count": len(claims),
                "evidence_reference_count": evidence_reference_count,
            },
        ),
        _dimension_score(
            "grounding_discipline",
            grounding_score,
            "Precise numeric claims must stay tightly grounded in the evidence pack rather than being invented during synthesis.",
            {
                "grounded_numeric_fact_count": len(grounded_numeric_facts),
                "unsupported_numeric_count": len(unsupported_numbers),
                "grounded_numeric_ratio": round(grounded_numeric_ratio, 3),
            },
        ),
        _dimension_score(
            "lateral_breadth",
            lateral_breadth_score,
            "Strong analysts test alternatives, counterarguments, hidden variables, and switch conditions.",
            {
                "adjacent_question_count": len(adjacent_questions),
                "adjacent_kind_count": unique_adjacent_kinds,
                "critique_findings": len(critique_findings),
                "decision_triggers": len(decision_triggers),
                "has_counterargument_language": int(has_counterargument_language),
                "has_hidden_variable_language": int(has_hidden_variable_language),
                "has_switch_language": int(has_switch_language),
            },
        ),
        _dimension_score(
            "decision_usefulness",
            decision_usefulness_score,
            "The report must help a real operator choose, sequence action, and understand what could change the call.",
            {
                "recommendation_bullets": len(recommendation_bullets),
                "evidence_linked_bullets": evidence_linked_bullets,
                "has_tradeoff_language": int(has_tradeoff_language),
                "has_option_space": int(has_option_space),
                "has_unknowns": int(has_unknowns),
                "has_roadmap": int(has_roadmap),
            },
        ),
        _dimension_score(
            "presentation_depth",
            presentation_score,
            "Analytical presentation quality is not cosmetics: structure, length, exhibits, and section depth shape usability.",
            {
                "word_count": word_count,
                "section_count": section_count,
                "exhibit_count": exhibit_count,
                "average_section_words": round(average_section_words, 1),
            },
        ),
    ]

    weighted_score = (
        0.11 * dimensions[0].score
        + 0.11 * dimensions[1].score
        + 0.07 * dimensions[2].score
        + 0.14 * dimensions[3].score
        + 0.14 * dimensions[4].score
        + 0.10 * dimensions[5].score
        + 0.09 * dimensions[6].score
        + 0.10 * dimensions[7].score
        + 0.09 * dimensions[8].score
        + 0.05 * dimensions[9].score
    )
    overall_score = round(_clamp(weighted_score - overclaim_penalty), 2)

    if overall_score >= 85:
        verdict = "agency_grade"
    elif overall_score >= 75:
        verdict = "strong"
    elif overall_score >= 65:
        verdict = "usable"
    else:
        verdict = "thin"

    sorted_dimensions = sorted(dimensions, key=lambda item: item.score)
    strengths = [
        f"{item.dimension.replace('_', ' ')} is comparatively strong at {item.score:.1f}/100."
        for item in sorted(dimensions, key=lambda score_item: score_item.score, reverse=True)
        if item.score >= 75
    ][:4]

    weaknesses = []
    for item in sorted_dimensions[:4]:
        if item.score >= 75:
            continue
        weaknesses.append(f"{item.dimension.replace('_', ' ')} is weak at {item.score:.1f}/100.")

    rewrite_priorities: list[str] = []
    low_dimensions = {item.dimension: item.score for item in sorted_dimensions[:4]}
    if low_dimensions.get("topic_alignment", 100.0) < 75:
        rewrite_priorities.append("Tighten topical alignment: remove semantically off-target sources and keep the report anchored to the actual decision question.")
    if low_dimensions.get("coverage", 100.0) < 75:
        rewrite_priorities.append("Close uncovered core questions or explicitly narrow the thesis so the recommendation is honest.")
    if low_dimensions.get("claim_depth", 100.0) < 75:
        rewrite_priorities.append("Increase non-trivial claims: quantified comparisons, boundary conditions, counterarguments, and causal explanations.")
    if low_dimensions.get("source_authority", 100.0) < 75 or low_dimensions.get("source_diversity", 100.0) < 75:
        rewrite_priorities.append("Bring in more authoritative and diverse sources, especially official docs, benchmarks, and mature project material.")
    if low_dimensions.get("grounding_discipline", 100.0) < 80:
        rewrite_priorities.append("Remove invented precise numbers and keep every material metric anchored to claims already supported in the evidence pack.")
    if low_dimensions.get("lateral_breadth", 100.0) < 75:
        rewrite_priorities.append("Expand alternatives, anti-thesis, hidden variables, and recommendation-switch conditions.")
    if low_dimensions.get("decision_usefulness", 100.0) < 75:
        rewrite_priorities.append("Sharpen decision utility with evidence-linked recommendations, explicit tradeoffs, and clearer next-step sequencing.")
    if low_dimensions.get("presentation_depth", 100.0) < 75:
        rewrite_priorities.append("Increase section depth, exhibits, and analytical density rather than adding filler.")
    if not rewrite_priorities:
        rewrite_priorities.append("Preserve the strongest analytical sections and tighten weak wording without diluting evidence.")

    metrics = {
        "source_count": source_count,
        "topic_alignment_score": round(topic_alignment_score, 2),
        "source_alignment_ratio": round(source_alignment_ratio, 3),
        "average_source_reliability": round(average_reliability, 3),
        "strong_source_ratio": round(strong_source_ratio, 3),
        "unique_domains": unique_domains,
        "coverage_ratio": round(coverage.coverage_ratio, 3),
        "claim_count": len(claims),
        "nontrivial_claim_count": nontrivial_claims,
        "nontrivial_claim_ratio": round(nontrivial_ratio, 3),
        "evidence_count": len(evidence),
        "grounded_numeric_fact_count": len(grounded_numeric_facts),
        "unsupported_numeric_count": len(unsupported_numbers),
        "grounded_numeric_ratio": round(grounded_numeric_ratio, 3),
        "adjacent_question_count": len(adjacent_questions),
        "decision_trigger_count": len(decision_triggers),
        "word_count": word_count,
        "section_count": section_count,
        "exhibit_count": exhibit_count,
        "overclaim_penalty": round(overclaim_penalty, 2),
    }

    return QualityAssessment(
        overall_score=overall_score,
        verdict=verdict,
        strengths=strengths,
        weaknesses=weaknesses or ["No dominant weakness was detected, but the report can still be tightened."],
        rewrite_priorities=rewrite_priorities,
        dimensions=dimensions,
        metrics=metrics,
    )


def build_revision_focus(assessment: QualityAssessment, max_items: int = 4) -> list[str]:
    actionable_dimensions = [
        item for item in sorted(assessment.dimensions, key=lambda item: item.score)
        if item.dimension in _ACTIONABLE_REVISION_DIMENSIONS
    ]
    weakest_dimensions = actionable_dimensions[:max_items]
    focus = [item.dimension.replace("_", " ") for item in weakest_dimensions]
    for priority in assessment.rewrite_priorities:
        if len(focus) >= max_items:
            break
        lowered = priority.lower()
        if "authoritative and diverse sources" in lowered or "uncovered core questions" in lowered:
            continue
        focus.append(priority)
    if not focus:
        focus.extend(["decision usefulness", "presentation depth"])
    return list(dict.fromkeys(focus))


def build_quality_iteration(
    iteration: int,
    assessment: QualityAssessment,
    *,
    previous_score: float | None = None,
    improved: bool | None = None,
    revision_focus: list[str] | None = None,
    consecutive_improvements: int = 0,
    notes: list[str] | None = None,
) -> QualityIteration:
    delta = round(assessment.overall_score - previous_score, 2) if previous_score is not None else 0.0
    return QualityIteration(
        iteration=iteration,
        assessment=assessment,
        delta_from_previous=delta,
        improved=bool(improved if improved is not None else (previous_score is not None and delta > 0)),
        consecutive_improvements=consecutive_improvements,
        revision_focus=revision_focus or [],
        notes=notes or [],
    )
