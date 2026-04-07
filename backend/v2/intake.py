from __future__ import annotations

import re

from backend.v2.models import (
    ArtifactFormat,
    BudgetTier,
    ClarificationField,
    ClarificationPack,
    ClarificationQuestion,
    ReportType,
    RequestSpec,
    SourceType,
    TaskSpec,
)
from backend.v2.reference_data import match_reference_pack


_DECISION_HINTS = (
    "choose",
    "select",
    "buy",
    "adopt",
    "pick",
    "procure",
    "decide",
    "evaluate",
    "compare",
    "выбрать",
    "сравни",
    "оцен",
    "решен",
    "внедр",
)


def detect_language(text: str) -> str:
    return "ru" if re.search(r"[\u0400-\u04FF]", text or "") else "en"


def normalize_budget_tier(depth: str | None) -> BudgetTier:
    if depth == "light":
        return BudgetTier.LIGHT
    if depth == "deep":
        return BudgetTier.DEEP
    if depth == "exhaustive":
        return BudgetTier.EXHAUSTIVE
    return BudgetTier.STANDARD


def classify_report_type(query: str) -> ReportType:
    normalized = (query or "").lower()
    if any(token in normalized for token in ("competitive scan", "competitor", "конкурент", "competitive")):
        return ReportType.COMPETITIVE_SCAN
    if any(token in normalized for token in ("benchmark", "leaderboard", "бенчмарк", "benchmarking")):
        return ReportType.BENCHMARK_SUMMARY
    if any(token in normalized for token in ("vendor", "tool", "platform", "compare", "vs", "versus", "сравн", "платформ")):
        return ReportType.VENDOR_EVALUATION
    if any(token in normalized for token in ("market", "landscape", "рынок", "ландшафт")):
        return ReportType.MARKET_LANDSCAPE
    if any(token in normalized for token in ("strategic", "strategy", "brief", "стратег", "бриф")):
        return ReportType.STRATEGIC_BRIEF
    return ReportType.GENERAL_ANALYSIS


def infer_subject(query: str) -> str:
    cleaned = " ".join((query or "").split()).strip()
    cleaned = re.sub(r"^(compare|evaluate|analyze|assess|prepare|run)\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^(сравни|сравнить|оцени|оценить|проанализируй|подготовь)\s+", "", cleaned, flags=re.IGNORECASE)
    if len(cleaned) <= 180:
        return cleaned or "Unspecified subject"
    lower = cleaned.lower()
    for marker in (" that ", " which ", " by ", " with explicit ", " with ", ". "):
        index = lower.find(marker)
        if 42 <= index <= 132:
            concise = cleaned[:index].rstrip(" ,;:-")
            if len(concise.split()) >= 5:
                return concise
    fragments: list[str] = []
    for marker in ("build-vs-buy", "managed search apis", "orchestration frameworks"):
        index = lower.find(marker)
        if index < 0:
            continue
        fragment = cleaned[max(0, index - 12): min(len(cleaned), index + len(marker) + 24)].strip(" ,;:-")
        if fragment and fragment not in fragments:
            fragments.append(fragment)
    if fragments:
        lead = cleaned[:78].rstrip(" ,;:-")
        tail = " | ".join(fragments)[:96].strip(" ,;:-")
        return f"{lead} ... {tail}"[:180] or "Unspecified subject"
    head = cleaned[:140].rstrip(" ,;:-")
    tail = cleaned[-35:].lstrip(" ,;:-")
    return f"{head} ... {tail}"[:180] or "Unspecified subject"


def infer_geography(query: str) -> str:
    normalized = (query or "").lower()
    if any(token in normalized for token in ("russia", "росси", "cis", "снг")):
        return "russia_cis"
    if any(token in normalized for token in ("europe", "eu", "европ")):
        return "europe"
    if any(token in normalized for token in ("usa", "united states", "сша")):
        return "united_states"
    if any(token in normalized for token in ("global", "world", "мир", "глобал")):
        return "global"
    return "global"


def infer_time_horizon(query: str) -> str:
    years = re.findall(r"(20\d{2})", query or "")
    if years:
        unique = sorted(set(years))
        return f"{unique[0]}-{unique[-1]}" if len(unique) > 1 else unique[0]
    return "current"


def _query_has_any(query: str, tokens: tuple[str, ...]) -> bool:
    lowered = (query or "").lower()
    return any(token in lowered for token in tokens)


def infer_must_cover_questions(request_spec: RequestSpec, evaluation_dimensions: list[str]) -> list[str]:
    query = request_spec.original_query
    subject = request_spec.subject
    dimensions = ", ".join(evaluation_dimensions[:3]) if evaluation_dimensions else "quality, cost, risk"
    llm_tokens = ("llm", "model", "models", "gpt", "claude", "qwen", "deepseek", "gemini", "сонар", "модел")
    github_tokens = ("github", "open-source", "opensource", "repo", "repository", "git")
    search_tokens = ("search", "web search", "deep research", "research", "retrieval", "rag", "поиск", "исслед")

    if request_spec.language == "ru":
        if _query_has_any(query, llm_tokens) and _query_has_any(query, github_tokens) and _query_has_any(query, search_tokens):
            return [
                f"Какие LLM-модели реально являются сильнейшими кандидатами для {subject}?",
                f"Какие GitHub-проекты достаточно зрелые, чтобы использовать их для поиска, deep research или orchestration в рамках {subject}?",
                f"Какой стек и архитектурная связка лучше всего решают задачу '{request_spec.decision_context}' и чем она сильнее Perplexity?",
                f"Какие trade-offs, риски и условия переключения рекомендации критичны по осям {dimensions}?",
            ]
        return [
            f"Какое конкретное решение должен поддержать отчёт по теме '{subject}'?",
            f"Какие реальные альтернативы нужно сравнить по осям {dimensions}?",
            f"Какой вариант или стек лучше всего решает задачу '{request_spec.decision_context}'?",
            f"Какие trade-offs, риски и условия переключения рекомендации подтверждаются фактами?",
        ]

    if _query_has_any(query, llm_tokens) and _query_has_any(query, github_tokens) and _query_has_any(query, search_tokens):
        return [
            f"Which LLM models are the strongest real candidates for {subject}?",
            f"Which GitHub projects are mature enough to use for search, deep research, or orchestration in the context of {subject}?",
            f"Which stack and architecture best satisfy '{request_spec.decision_context}' and outperform Perplexity on the target criteria?",
            f"What tradeoffs, risks, and recommendation-switch conditions matter most across {dimensions}?",
        ]
    return [
        f"What concrete decision should this report support for '{subject}'?",
        f"What credible alternatives should be compared across {dimensions}?",
        f"Which option or stack best supports '{request_spec.decision_context}'?",
        "What are the strongest evidence-backed tradeoffs, risks, and decision triggers?",
    ]


def build_request_spec(query: str, *, depth: str | None = None) -> RequestSpec:
    pack = match_reference_pack(query)
    report_type = pack.report_type if pack else classify_report_type(query)
    subject = pack.title if pack else infer_subject(query)
    has_decision_context = any(token in (query or "").lower() for token in _DECISION_HINTS)
    missing: list[str] = []
    if len((query or "").split()) < 4:
        missing.append("subject_scope")
    if not has_decision_context:
        missing.append("decision_context")

    decision_context = (
        "Support a concrete vendor or platform choice."
        if has_decision_context and report_type == ReportType.VENDOR_EVALUATION
        else "Support a decision with evidence-backed synthesis."
    )

    return RequestSpec(
        original_query=query,
        language=detect_language(query),
        report_type=report_type,
        goal="Produce an evidence-backed analytical report for a real decision.",
        subject=subject,
        decision_context=decision_context,
        target_audience="operator",
        time_horizon=infer_time_horizon(query),
        geography=infer_geography(query),
        quality_target="decision-grade",
        budget_tier=normalize_budget_tier(depth),
        missing_critical_fields=missing,
    )


def build_clarification_pack(run_id: str, request_spec: RequestSpec) -> ClarificationPack:
    pack = match_reference_pack(request_spec.original_query)
    questions: list[ClarificationQuestion] = [
        ClarificationQuestion(
            question_id="decision-context",
            field=ClarificationField.DECISION_CONTEXT,
            prompt=(
                "Какое конкретное решение должен поддержать отчёт?"
                if request_spec.language == "ru"
                else "What concrete decision should this report support?"
            ),
            rationale="The report should optimize for a decision, not generic research.",
            placeholder="e.g. choose a primary platform for a 6-month rollout",
        )
    ]

    if pack and pack.evaluation_dimensions:
        questions.append(
            ClarificationQuestion(
                question_id="dimensions",
                field=ClarificationField.EVALUATION_DIMENSIONS,
                prompt=(
                    "Какие критерии для вас важнее всего?"
                    if request_spec.language == "ru"
                    else "Which evaluation dimensions matter most?"
                ),
                rationale="Dimensions should be explicit before research planning.",
                placeholder=", ".join(pack.evaluation_dimensions[:4]),
            )
        )

    questions.append(
        ClarificationQuestion(
            question_id="geography",
            field=ClarificationField.GEOGRAPHY,
            prompt=(
                "Нужен глобальный анализ или фокус на конкретном регионе?"
                if request_spec.language == "ru"
                else "Should this stay global or focus on a specific region?"
            ),
            rationale="Geography changes source targeting and freshness requirements.",
            placeholder="global / US / Europe / Russia+CIS",
            required=False,
        )
    )
    questions.append(
        ClarificationQuestion(
            question_id="budget",
            field=ClarificationField.BUDGET,
            prompt=(
                "Есть ли жёсткие ограничения по стоимости, лицензии или приватности?"
                if request_spec.language == "ru"
                else "Are there hard constraints on cost, licensing, or privacy?"
            ),
            rationale="Constraints belong in TaskSpec, not buried in free text.",
            placeholder="e.g. open weights only, EU hosting, under $20k/year",
            required=False,
        )
    )
    return ClarificationPack(run_id=run_id, request_spec=request_spec, questions=questions[:5])


def build_task_spec(request_spec: RequestSpec, *, answers: dict[str, str] | None = None) -> TaskSpec:
    answers = answers or {}
    pack = match_reference_pack(request_spec.original_query)

    raw_dimensions = answers.get("dimensions", "")
    if raw_dimensions.strip():
        evaluation_dimensions = [item.strip() for item in re.split(r"[,;/\n]", raw_dimensions) if item.strip()]
    elif pack:
        evaluation_dimensions = pack.evaluation_dimensions[:]
    else:
        evaluation_dimensions = (
            ["качество", "стоимость", "операционный риск", "простота внедрения"]
            if request_spec.language == "ru"
            else ["quality", "cost", "operational risk", "integration fit"]
        )

    constraints = [item for item in [answers.get("budget", "").strip()] if item]
    decision_context = answers.get("decision-context", "").strip() or request_spec.decision_context
    geography = answers.get("geography", "").strip()
    if geography:
        request_spec.geography = geography
    request_spec.decision_context = decision_context

    must_cover_questions = pack.must_cover_questions[:] if pack else infer_must_cover_questions(request_spec, evaluation_dimensions)

    budget_limits = {
        BudgetTier.LIGHT: 0.5,
        BudgetTier.STANDARD: 2.0,
        BudgetTier.DEEP: 5.0,
        BudgetTier.EXHAUSTIVE: 10.0,
    }

    return TaskSpec(
        request_spec=request_spec,
        success_criteria=[
            "Every recommendation must be tied to evidence.",
            "Weak-source discovery hints cannot dominate the recommendation.",
            "Limitations and unresolved gaps must be explicit.",
        ],
        evaluation_dimensions=evaluation_dimensions,
        constraints=constraints,
        must_cover_questions=must_cover_questions,
        allowed_source_types=[
            SourceType.OFFICIAL_DOCUMENTATION,
            SourceType.VENDOR_PAGE,
            SourceType.BENCHMARK,
            SourceType.RESEARCH_PAPER,
            SourceType.HIGH_QUALITY_SECONDARY,
        ],
        blocked_source_types=[SourceType.WEAK_SECONDARY],
        output_package=[
            ArtifactFormat.MARKDOWN,
            ArtifactFormat.HTML,
            ArtifactFormat.PDF,
            ArtifactFormat.DOCX,
            ArtifactFormat.JSON,
        ],
        max_budget_usd=budget_limits[request_spec.budget_tier],
        answers=answers,
    )
