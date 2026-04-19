"""Pydantic v2 schemas — the single source of truth for the pipeline."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SourceType = Literal["academic", "official", "industry", "media", "other"]
ScoutStrategy = Literal["search", "extract"]
CrossLinkType = Literal[
    "paradox",
    "causal_chain",
    "shared_mechanism",
    "unexpected_confirmation",
]


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Question(_Base):
    text: str
    id: str


class ScoutTask(_Base):
    cell_id: str
    query: str
    target_sources: list[str] = Field(default_factory=list)
    strategy: ScoutStrategy = "search"
    target_urls: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_extract_has_urls(self) -> "ScoutTask":
        if self.strategy == "extract" and not self.target_urls:
            raise ValueError(
                "strategy='extract' requires at least one entry in target_urls"
            )
        return self


class Finding(_Base):
    claim: str
    number: str | None = None
    source_url: str
    source_type: SourceType
    verbatim_quote: str | None = None


class Cell(_Base):
    id: str
    domain: str
    layer: str
    scout_task: ScoutTask


class Matrix(_Base):
    question_id: str
    domains: list[str]
    cells: list[Cell]


class Block(_Base):
    cell_id: str
    conclusion: str
    strongest_number: str | None = None
    gap: str | None = None
    key_assumptions: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    variables: list[str] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)


class CrossLink(_Base):
    cell_a: str
    cell_b: str
    shared_variable: str
    type: CrossLinkType
    insight: str
    evidence_pointers: list[str] = Field(default_factory=list)


class TopNumber(_Base):
    value: str
    context: str
    source_url: str


class KeyTension(_Base):
    tension: str
    pole_a: str
    pole_b: str


class ExecutiveSummary(_Base):
    main_finding: str
    top_numbers: list[TopNumber] = Field(default_factory=list)
    key_tensions: list[KeyTension] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)


class Report(_Base):
    question: Question
    matrix: Matrix
    blocks: list[Block]
    cross_links: list[CrossLink]
    summary: ExecutiveSummary | None = None
    metadata: dict = Field(default_factory=dict)


# --- v4 schemas ---
# v4 is a meta-analysis layer bolted on top of v3. v3 schemas above are untouched.
# Track A owns: ResearchPrompt, UploadedMarkdown, V4Session, V4Status.
# Track B will extend AnalysisOutput and FinalReport with real fields (extra="allow"
# keeps them forward-compatible until then).

V4Status = Literal[
    "created",
    "prompt_ready",
    "reports_uploaded",
    "analyzed",
    "dobor_uploaded",
    "synthesized",
]

DetectedTool = Literal["perplexity", "openai_dr", "claude", "other"]


class _V4Base(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ResearchPrompt(_V4Base):
    full_prompt: str
    reasoning: str
    expected_structure: list[str] = Field(default_factory=list)
    key_entities: list[str] = Field(default_factory=list)
    tips_for_search: str = ""


class UploadedMarkdown(_V4Base):
    filename: str
    content: str
    detected_tool: DetectedTool | None = None
    word_count: int = 0


# --- v4 Track B schemas ---

Confidence = Literal["high", "medium", "low"]
ConflictImportance = Literal["critical", "material", "minor"]
FollowupIntent = Literal["fill_gap", "verify_number", "resolve_conflict"]
FollowupTool = Literal["perplexity", "openai_dr", "claude"]
FollowupPriority = Literal["must", "nice"]
SourceReliability = Literal["high", "medium", "low"]


class SourceSummary(_V4Base):
    source: str
    summary: str
    strengths: str = ""
    weaknesses: str = ""


class ConsensusClaim(_V4Base):
    claim: str
    supporting_sources: list[str] = Field(default_factory=list)
    confidence: Confidence = "medium"


class Conflict(_V4Base):
    topic: str
    source_a: str
    claim_a: str
    source_b: str
    claim_b: str
    resolution_hint: str = ""
    importance: ConflictImportance = "material"


class Gap(_V4Base):
    topic: str
    why_critical: str
    what_to_find: str
    candidate_sources: list[str] = Field(default_factory=list)


class UnverifiedNumber(_V4Base):
    value: str
    metric: str
    subject: str
    source_tool: str
    why_unverified: str = ""


class FollowupPrompt(_V4Base):
    prompt_id: str
    intent: FollowupIntent
    prompt: str
    target_info: str = ""
    suggested_tool: FollowupTool = "perplexity"
    suggested_source_site: str = ""
    priority: FollowupPriority = "must"
    linked_to: str = ""


class AnalysisOutput(_V4Base):
    per_source_summary: list[SourceSummary] = Field(default_factory=list)
    consensus: list[ConsensusClaim] = Field(default_factory=list)
    conflicts: list[Conflict] = Field(default_factory=list)
    gaps: list[Gap] = Field(default_factory=list)
    unverified_numbers: list[UnverifiedNumber] = Field(default_factory=list)
    quality_notes: str = ""
    # Canonical single followup prompt — one DR run covers all gaps and conflicts.
    # Populated by Analyzer v4.1+. If present, this is the source of truth.
    followup_prompt: FollowupPrompt | None = None
    # Legacy list kept for backward-compat with old readers.
    # Shim: populated as [followup_prompt] when new field is present.
    followup_prompts: list[FollowupPrompt] = Field(default_factory=list)


class KeyNumber(_V4Base):
    value: str
    metric: str
    subject: str = ""
    source_url: str = ""


# --- v4 Track A structured output models ---


class QAItem(_V4Base):
    """Direct answer to one of the user's sub-questions."""

    question: str  # one of the user's sub-questions (from prompt analysis)
    answer: str  # direct 2-3 sentence answer
    details_ref: str  # where to find full detail in the report


class RankingItem(_V4Base):
    """Structured ranking entry for comparison/prioritization questions."""

    label: str
    weight: int | None = None  # e.g. 45 if OpenAI-DR-style, else None
    rationale: str
    evidence_strength: Literal["high", "medium", "low"]


class Table(_V4Base):
    """Structured table for comparative data."""

    title: str
    columns: list[str]
    rows: list[list[str]]
    caption: str | None = None
    source_ref: str | None = None


class ChartSpec(_V4Base):
    """Spec for generating a chart — not the rendered chart itself."""

    chart_type: Literal["bar", "line", "pie", "scatter", "stacked_bar", "waterfall"]
    title: str
    data: dict  # structure depends on chart_type
    x_label: str | None = None
    y_label: str | None = None
    caption: str | None = None


class CalloutBlock(_V4Base):
    """Highlighted insight, warning, key number, or note."""

    kind: Literal["insight", "warning", "key_number", "note"]
    title: str
    body: str


class KeyNumberHighlight(_V4Base):
    """Headline-level number for visual highlight on executive summary page."""

    value: str  # e.g. "883.8 тыс. руб./м²"
    label: str  # e.g. "средняя цена Prime Park H1 2025"
    source_ref: str  # e.g. "РБК Недвижимость"
    importance: Literal["headline", "primary", "secondary"]


class ExecutiveSummaryV4(_V4Base):
    main_answer: str
    ranking: str | None = None
    top_findings: list[str] = Field(default_factory=list)
    key_numbers: list[KeyNumber] = Field(default_factory=list)
    confidence_note: str = ""
    what_meta_adds: str = ""


class Source(_V4Base):
    title: str
    url: str = ""
    tool: str = ""
    reliability: SourceReliability = "medium"


# --- v4 Track A structured output models (added by Track B for contract) ---


class QAItem(_V4Base):
    """Direct answer to one of the user's sub-questions."""

    question: str  # one of the user's sub-questions (from prompt analysis)
    answer: str  # direct 2-3 sentence answer
    details_ref: str  # where to find full detail in the report


class RankingItem(_V4Base):
    """Structured ranking entry for comparison/prioritization questions."""

    label: str
    weight: int | None = None  # e.g. 45 if OpenAI-DR-style, else None
    rationale: str
    evidence_strength: Literal["high", "medium", "low"]


class Table(_V4Base):
    """Structured table for comparative data."""

    title: str
    columns: list[str]
    rows: list[list[str]]
    caption: str | None = None
    source_ref: str | None = None


class ChartSpec(_V4Base):
    """Spec for generating a chart — not the rendered chart itself."""

    chart_type: Literal["bar", "line", "pie", "scatter", "stacked_bar", "waterfall"]
    title: str
    data: dict  # structure depends on chart_type
    x_label: str | None = None
    y_label: str | None = None
    caption: str | None = None


class CalloutBlock(_V4Base):
    """Highlighted insight, warning, key number, or note."""

    kind: Literal["insight", "warning", "key_number", "note"]
    title: str
    body: str


class KeyNumberHighlight(_V4Base):
    """Headline-level number for visual highlight on executive summary page."""

    value: str  # e.g. "883.8 тыс. руб./м²"
    label: str  # e.g. "средняя цена Prime Park H1 2025"
    source_ref: str  # e.g. "РБК Недвижимость"
    importance: Literal["headline", "primary", "secondary"]


class FinalReport(_V4Base):
    session_id: str
    question: str
    research_prompt_used: str = ""
    executive_summary: ExecutiveSummaryV4
    main_synthesis: str = ""
    consensus_section: str = ""
    conflicts_section: str = ""
    gaps_filled_section: str = ""
    all_sources: list[Source] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)

    # --- NEW optional fields (Track A structured output, backward-compat) ---
    qa_section: list[QAItem] = Field(default_factory=list)
    ranking: list[RankingItem] = Field(default_factory=list)
    tables: list[Table] = Field(default_factory=list)
    charts: list[ChartSpec] = Field(default_factory=list)
    callouts: list[CalloutBlock] = Field(default_factory=list)
    key_numbers_highlight: list[KeyNumberHighlight] = Field(default_factory=list)
    cover_image_prompt: str | None = None


class V4Session(_V4Base):
    session_id: str
    raw_question: str
    research_prompt: ResearchPrompt | None = None
    source_reports: list[UploadedMarkdown] = Field(default_factory=list)
    analysis: AnalysisOutput | None = None
    followup_reports: list[UploadedMarkdown] = Field(default_factory=list)
    final_report: FinalReport | None = None
    status: V4Status = "created"
    created_at: datetime
    total_cost_rub: float = 0.0


V4Session.model_rebuild()
FinalReport.model_rebuild()
AnalysisOutput.model_rebuild()
