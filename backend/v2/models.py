from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RunStatus(str, Enum):
    DRAFT = "draft"
    AWAITING_SCOPE = "awaiting_scope"
    AWAITING_HANDOFF = "awaiting_handoff"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ReportType(str, Enum):
    VENDOR_EVALUATION = "vendor_evaluation"
    MARKET_LANDSCAPE = "market_landscape"
    BENCHMARK_SUMMARY = "benchmark_summary"
    STRATEGIC_BRIEF = "strategic_brief"
    COMPETITIVE_SCAN = "competitive_scan"
    GENERAL_ANALYSIS = "general_analysis"


class BudgetTier(str, Enum):
    LIGHT = "light"
    STANDARD = "standard"
    DEEP = "deep"
    EXHAUSTIVE = "exhaustive"


class SourceType(str, Enum):
    OFFICIAL_DOCUMENTATION = "official_documentation"
    VENDOR_PAGE = "vendor_page"
    GOVERNMENT = "government"
    RESEARCH_PAPER = "research_paper"
    BENCHMARK = "benchmark"
    USER_MATERIAL = "user_material"
    HIGH_QUALITY_SECONDARY = "high_quality_secondary"
    WEAK_SECONDARY = "weak_secondary"


class ArtifactFormat(str, Enum):
    MARKDOWN = "md"
    HTML = "html"
    PDF = "pdf"
    DOCX = "docx"
    JSON = "json"
    PPTX = "pptx"


class ClarificationField(str, Enum):
    DECISION_CONTEXT = "decision_context"
    EVALUATION_DIMENSIONS = "evaluation_dimensions"
    DEPLOYMENT_MODE = "deployment_mode"
    GEOGRAPHY = "geography"
    TIME_HORIZON = "time_horizon"
    SOURCE_POLICY = "source_policy"
    BUDGET = "budget"
    OUTPUT_PREFERENCE = "output_preference"


class QuestionKind(str, Enum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    ADJACENT_ALTERNATIVE = "adjacent_alternative"
    ADJACENT_COUNTERARGUMENT = "adjacent_counterargument"
    ADJACENT_HIDDEN_VARIABLE = "adjacent_hidden_variable"
    ADJACENT_BOUNDARY = "adjacent_boundary"
    ADJACENT_STAKEHOLDER = "adjacent_stakeholder"
    ADJACENT_TIME_SHIFT = "adjacent_time_shift"


class CritiqueKind(str, Enum):
    WEAK_EVIDENCE = "weak_evidence"
    OMITTED_QUESTION = "omitted_question"
    MISSING_COMPARATOR = "missing_comparator"
    BOUNDARY_CONDITION = "boundary_condition"
    DECISION_RISK = "decision_risk"


class SpendCategory(str, Enum):
    RESEARCH = "research"
    REVIEW = "review"
    WRITER = "writer"
    QUALITY_REVISION = "quality_revision"
    COMPLIANCE_REVISION = "compliance_revision"
    PRESENTATION = "presentation"
    STORAGE = "storage"


class MaterialKind(str, Enum):
    USER_UPLOAD = "user_upload"
    EXTERNAL_RESEARCH = "external_research"
    NOTE = "note"


class RunEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    step: str
    status: str
    message: str = ""
    timestamp: datetime = Field(default_factory=utc_now)
    payload: dict[str, Any] = Field(default_factory=dict)


class RequestSpec(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid4()))
    original_query: str
    language: str = "en"
    report_type: ReportType = ReportType.GENERAL_ANALYSIS
    goal: str
    subject: str
    decision_context: str = ""
    target_audience: str = "operator"
    time_horizon: str = "current"
    geography: str = "global"
    quality_target: str = "decision-grade"
    budget_tier: BudgetTier = BudgetTier.STANDARD
    missing_critical_fields: list[str] = Field(default_factory=list)


class ClarificationQuestion(BaseModel):
    question_id: str
    field: ClarificationField
    prompt: str
    rationale: str
    placeholder: str = ""
    required: bool = True


class ClarificationPack(BaseModel):
    run_id: str
    request_spec: RequestSpec
    questions: list[ClarificationQuestion] = Field(default_factory=list)


class TaskSpec(BaseModel):
    task_id: str = Field(default_factory=lambda: str(uuid4()))
    request_spec: RequestSpec
    success_criteria: list[str] = Field(default_factory=list)
    evaluation_dimensions: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    must_cover_questions: list[str] = Field(default_factory=list)
    allowed_source_types: list[SourceType] = Field(default_factory=list)
    blocked_source_types: list[SourceType] = Field(default_factory=list)
    output_package: list[ArtifactFormat] = Field(default_factory=list)
    max_budget_usd: float = 0.0
    answers: dict[str, str] = Field(default_factory=dict)
    allow_perplexity_handoff: bool = False
    material_ids: list[str] = Field(default_factory=list)


class DepthProfile(BaseModel):
    name: str
    label: str
    description: str
    research_depth: str
    initial_research_branches: int = 0
    source_limit: int = 0
    adjacent_question_limit: int = 0
    adjacent_research_branches: int = 0
    validation_research_branches: int = 0
    stack_backfill_limit: int = 0
    quality_revision_target: int = 0
    quality_max_rounds: int = 0
    prefer_perplexity_writer: bool = False


class SpendEntry(BaseModel):
    entry_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=utc_now)
    category: SpendCategory
    stage: str
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    pricing_basis: str = "estimated"
    notes: str = ""


class MaterialRecord(BaseModel):
    material_id: str = Field(default_factory=lambda: str(uuid4()))
    kind: MaterialKind = MaterialKind.USER_UPLOAD
    title: str
    filename: str
    stored_filename: str = ""
    text_filename: str = ""
    media_type: str = "text/plain"
    size_bytes: int = 0
    text_length: int = 0
    excerpt: str = ""
    uploaded_at: datetime = Field(default_factory=utc_now)


class PerplexityHandoffPrompt(BaseModel):
    prompt_id: str = Field(default_factory=lambda: str(uuid4()))
    stage: str
    title: str
    rationale: str = ""
    prompt: str


class ResearchQuestion(BaseModel):
    question_id: str
    question: str
    kind: QuestionKind = QuestionKind.PRIMARY
    priority: int = 1
    required_evidence_count: int = 2


class AdjacentQuestionCandidate(BaseModel):
    candidate_id: str = Field(default_factory=lambda: str(uuid4()))
    question: str
    kind: QuestionKind
    decision_impact: float = 0.0
    coverage_gap: float = 0.0
    novelty: float = 0.0
    comparative_value: float = 0.0
    research_cost: float = 0.0
    composite_score: float = 0.0
    selection_reason: str = ""


class CritiqueFinding(BaseModel):
    finding_id: str = Field(default_factory=lambda: str(uuid4()))
    kind: CritiqueKind
    severity: str = "medium"
    summary: str
    rationale: str = ""
    affected_claim_ids: list[str] = Field(default_factory=list)
    follow_up_question_ids: list[str] = Field(default_factory=list)


class DecisionTrigger(BaseModel):
    trigger_id: str = Field(default_factory=lambda: str(uuid4()))
    label: str
    condition: str
    implication: str
    confidence: float = 0.0


class ResearchPlan(BaseModel):
    primary_questions: list[ResearchQuestion] = Field(default_factory=list)
    secondary_questions: list[ResearchQuestion] = Field(default_factory=list)
    adjacent_question_candidates: list[AdjacentQuestionCandidate] = Field(default_factory=list)
    selected_adjacent_questions: list[ResearchQuestion] = Field(default_factory=list)
    claims_to_validate: list[str] = Field(default_factory=list)
    claims_to_disprove: list[str] = Field(default_factory=list)
    required_evidence_per_question: dict[str, int] = Field(default_factory=dict)
    suggested_search_queries: list[str] = Field(default_factory=list)
    preferred_domains: list[str] = Field(default_factory=list)
    required_source_mix: list[SourceType] = Field(default_factory=list)
    chart_candidates: list[str] = Field(default_factory=list)
    stop_conditions: list[str] = Field(default_factory=list)


class SearchCandidate(BaseModel):
    candidate_id: str = Field(default_factory=lambda: str(uuid4()))
    question_id: str
    query: str
    url: str
    title: str
    snippet: str = ""
    domain: str
    provider: str


class SourceLedgerEntry(BaseModel):
    source_id: str = Field(default_factory=lambda: str(uuid4()))
    url: str
    title: str
    domain: str
    source_type: SourceType
    publisher: str = ""
    published_at: str = ""
    reliability_score: float = 0.0
    selection_reason: str
    question_links: list[str] = Field(default_factory=list)


class SourceSnapshot(BaseModel):
    source_id: str
    url: str
    title: str
    fetched_at: datetime = Field(default_factory=utc_now)
    content: str
    excerpt: str = ""
    provider: str = ""
    fetch_status: str = "ok"


class EvidenceRecord(BaseModel):
    evidence_id: str = Field(default_factory=lambda: str(uuid4()))
    question_id: str
    source_id: str
    claim: str
    snippet: str
    confidence: float = 0.0
    extraction_method: str = "heuristic"
    supports: list[str] = Field(default_factory=list)


class ClaimRecord(BaseModel):
    claim_id: str = Field(default_factory=lambda: str(uuid4()))
    statement: str
    question_id: str
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    contradiction_notes: list[str] = Field(default_factory=list)
    recommendation_safe: bool = False


class CoverageQuestionStatus(BaseModel):
    question_id: str
    question: str
    evidence_count: int = 0
    source_count: int = 0
    status: str = "gap"


class CoverageReport(BaseModel):
    total_questions: int
    covered_questions: int
    coverage_ratio: float
    strong_source_ratio: float
    contradiction_count: int
    questions: list[CoverageQuestionStatus] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


class AnalysisBrief(BaseModel):
    title: str
    executive_summary: str
    decision_context: str
    recommendation_posture: str
    key_findings: list[str] = Field(default_factory=list)
    key_risks: list[str] = Field(default_factory=list)
    option_space: list[str] = Field(default_factory=list)
    critical_unknowns: list[str] = Field(default_factory=list)
    decision_triggers: list[str] = Field(default_factory=list)
    improvement_priorities: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    uncertainty_statement: str = ""
    chart_candidates: list[str] = Field(default_factory=list)


class QualityDimensionScore(BaseModel):
    dimension: str
    score: float
    rationale: str = ""
    raw_metrics: dict[str, float | int | str] = Field(default_factory=dict)


class QualityAssessment(BaseModel):
    overall_score: float
    verdict: str
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    rewrite_priorities: list[str] = Field(default_factory=list)
    dimensions: list[QualityDimensionScore] = Field(default_factory=list)
    metrics: dict[str, float | int | str] = Field(default_factory=dict)


class QualityIteration(BaseModel):
    iteration: int
    assessment: QualityAssessment
    delta_from_previous: float = 0.0
    improved: bool = False
    consecutive_improvements: int = 0
    revision_focus: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class AuditSummary(BaseModel):
    release_status: str
    checks_passed: int
    checks_failed: int
    failures: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class RunSummary(BaseModel):
    run_id: str
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    request: str
    title: str = "Untitled report"
    status: RunStatus = RunStatus.DRAFT
    budget_tier: BudgetTier = BudgetTier.STANDARD
    cost_usd: float = 0.0
    tokens_used: int = 0
    report_url_map: dict[str, str] = Field(default_factory=dict)
    requested_output_formats: list[ArtifactFormat] = Field(default_factory=list)
    depth_profile: DepthProfile | None = None
    spend_breakdown: list[SpendEntry] = Field(default_factory=list)
    materials: list[MaterialRecord] = Field(default_factory=list)
    handoff_prompts: list[PerplexityHandoffPrompt] = Field(default_factory=list)
    allow_perplexity_handoff: bool = False
    request_spec: RequestSpec | None = None
    task_spec: TaskSpec | None = None
    analysis_brief: AnalysisBrief | None = None
    coverage_report: CoverageReport | None = None
    quality_assessment: QualityAssessment | None = None
    audit_summary: AuditSummary | None = None
