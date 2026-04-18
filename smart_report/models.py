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
    followup_prompts: list[FollowupPrompt] = Field(default_factory=list)


class KeyNumber(_V4Base):
    value: str
    metric: str
    subject: str = ""
    source_url: str = ""


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
