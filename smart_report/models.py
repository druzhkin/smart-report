"""Pydantic v2 schemas — the single source of truth for the pipeline.

v4.5 additions (schema-pipeline track):
  - SourceRef, Claim, NumericFact, QualitativeFact, CitedText, NumberedSource
  - NormalizedReport (Intake output)
  - AnalysisOutput extended with all_numeric_facts / high_relevance_facts
  - FinalReport extended with bibliography / citation_coverage / source_count
All new fields are optional / default-empty for backward compatibility.
"""

from __future__ import annotations

import hashlib
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


# ---------------------------------------------------------------------------
# v4 schemas
# ---------------------------------------------------------------------------
# v4 is a meta-analysis layer bolted on top of v3. v3 schemas above are untouched.

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


DecompositionMethod = Literal[
    "none",
    "domain_template_ru_re",
    "llm_planner",
    "llm_planner_failed",
]


class SubQuestion(_V4Base):
    """A single sub-question produced by the v4.5 Step 2.2 LLM planner.

    Each strategic query that doesn't match a domain template is
    decomposed into 3-5 of these. The analyst (or future auto-retrieval
    layer) can run each sub-question independently. ``depends_on``
    captures cases where one sub-question's answer is required to
    formulate or interpret another (e.g. "what is the regulatory
    baseline" must answer before "how does the proposed change shift
    competitive dynamics").
    """

    id: str  # "sq1", "sq2", ... — stable within a single decomposition
    text: str  # the sub-question itself (1-2 sentences, answerable)
    depends_on: list[str] = Field(default_factory=list)  # other SubQuestion ids
    rationale: str = ""  # why this sub-question matters for the parent query
    suggested_sources: list[str] = Field(default_factory=list)  # source-type hints


class ResearchPrompt(_V4Base):
    full_prompt: str
    reasoning: str
    expected_structure: list[str] = Field(default_factory=list)
    key_entities: list[str] = Field(default_factory=list)
    tips_for_search: str = ""
    # v4.5 Phase 2 Step 2.2 — decomposition trace (optional, defaults preserve
    # backward compat with prompts generated before Step 2.2 wiring).
    decomposition_method: DecompositionMethod = "none"
    sub_questions: list[SubQuestion] = Field(default_factory=list)


class UploadedMarkdown(_V4Base):
    filename: str
    content: str
    detected_tool: DetectedTool | None = None
    word_count: int = 0


# ---------------------------------------------------------------------------
# v4 Track B schemas
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# v4.5 Track 1+4 — citation & fact schemas
# ---------------------------------------------------------------------------


class SourceRef(BaseModel):
    """A single citable source — carries enough to build a bibliography entry."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    url: str
    title: str | None = None
    publisher: str | None = None
    date: str | None = None
    quote_excerpt: str | None = None
    accessed_via: str = "manual_upload"  # "perplexity_dr_1" | "openai_dr_1" | "manual_upload"
    confidence: Literal["primary", "secondary", "aggregator"] = "secondary"


class Claim(BaseModel):
    """A factual claim extracted from a source, with inline citations."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    text: str
    sources: list[SourceRef] = Field(default_factory=list)
    claim_type: Literal["numeric", "qualitative", "comparative", "directional"] = "qualitative"
    confidence_level: Literal["high", "medium", "low"] = "medium"


class NumericFact(BaseModel):
    """A single numeric fact with deterministic ID and source attribution.

    Fields added in v4.5 Track 4 (table parser path):
      - source_quote: verbatim quote from the source document (optional)
      - is_author_synthesis: True when the fact is marked as author synthesis
        rather than a directly cited data point (optional, default False)

    Both new fields are optional for full backward compatibility — the LLM
    fallback path leaves them unset (None / False).
    """

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    fact_id: str  # sha1(value|metric|subject)[:12]
    value: str
    metric: str
    subject: str
    timeframe: str | None = None
    sources: list[SourceRef] = Field(default_factory=list)
    relevance_to_question: Literal["high", "medium", "low", "tangential"] = "medium"
    fact_category: Literal[
        "price", "volume", "share", "growth_rate", "capex", "opex",
        "premium_pct", "area", "count", "ratio", "ranking_position", "other"
    ] = "other"
    # v4.5 Track 4 table-parser additions (optional, backward-compatible)
    source_quote: str | None = None
    is_author_synthesis: bool = False

    @staticmethod
    def make_id(value: str, metric: str, subject: str) -> str:
        """Deterministic fact_id = sha1(value|metric|subject)[:12]."""
        raw = f"{value}|{metric}|{subject}".encode()
        return hashlib.sha1(raw).hexdigest()[:12]


class QualitativeFact(BaseModel):
    """A non-numeric qualitative claim with source attribution."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    fact_id: str
    statement: str
    subject: str
    sources: list[SourceRef] = Field(default_factory=list)
    relevance_to_question: Literal["high", "medium", "low", "tangential"] = "medium"
    fact_category: Literal[
        "methodology", "case_study", "analogy", "definition",
        "expert_opinion", "comparison", "trend", "other"
    ] = "other"

    @staticmethod
    def make_id(statement: str, subject: str) -> str:
        raw = f"{statement[:80]}|{subject}".encode()
        return hashlib.sha1(raw).hexdigest()[:12]


class CitedText(BaseModel):
    """Text with inline [REF:source_id_x] markers and a source registry."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    text: str  # contains [REF:source_id_x] markers
    cited_sources: dict[str, SourceRef] = Field(default_factory=dict)


class NumberedSource(BaseModel):
    """A numbered bibliography entry produced by post-processing."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    number: int
    source_ref: SourceRef
    cited_in_sections: list[str] = Field(default_factory=list)


class NormalizedReport(BaseModel):
    """Output of the Intake step for a single uploaded markdown file.

    v4.5 Track 4 additions (backward-compatible, all default to neutral values):
      - facts_table_found: True when a "Сводная таблица данных" was parsed
        and used as the primary fact source (skipping LLM extraction).
      - facts_table_row_count: number of rows parsed from the table.
      - fallback_used: True when the LLM extraction path ran because no table
        was found (or the table was malformed / had zero valid rows).
    """

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    source_tool: Literal["perplexity_dr", "openai_dr", "claude_research", "valyu", "other"] = "other"
    source_filename: str
    raw_text: str
    extracted_claims: list[Claim] = Field(default_factory=list)
    extracted_sources_inventory: list[SourceRef] = Field(default_factory=list)
    extracted_numeric_facts: list[NumericFact] = Field(default_factory=list)
    extracted_qualitative_facts: list[QualitativeFact] = Field(default_factory=list)
    fact_count_summary: dict[str, int] = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)
    # v4.5 Track 4 table-parser tracking (optional, backward-compatible)
    facts_table_found: bool = False
    facts_table_row_count: int = 0
    fallback_used: bool = False  # True when LLM extraction ran (no table present)


# ---------------------------------------------------------------------------
# AnalysisOutput — extended with fact aggregation fields
# ---------------------------------------------------------------------------


class AnalysisOutput(_V4Base):
    per_source_summary: list[SourceSummary] = Field(default_factory=list)
    consensus: list[ConsensusClaim] = Field(default_factory=list)
    conflicts: list[Conflict] = Field(default_factory=list)
    gaps: list[Gap] = Field(default_factory=list)
    unverified_numbers: list[UnverifiedNumber] = Field(default_factory=list)
    quality_notes: str = ""
    # Canonical single followup prompt — one DR run covers all gaps and conflicts.
    followup_prompt: FollowupPrompt | None = None
    # Legacy list kept for backward-compat with old readers.
    followup_prompts: list[FollowupPrompt] = Field(default_factory=list)

    # v4.5 fact aggregation — populated by Intake+Analyzer pipeline
    all_numeric_facts: list[NumericFact] = Field(default_factory=list)
    all_qualitative_facts: list[QualitativeFact] = Field(default_factory=list)
    high_relevance_facts: list[NumericFact] = Field(default_factory=list)
    fact_coverage_target: int = 0


# ---------------------------------------------------------------------------
# v4 Track A structured output models
# ---------------------------------------------------------------------------


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
    key_numbers: list["KeyNumber"] = Field(default_factory=list)
    confidence_note: str = ""
    what_meta_adds: str = ""


class KeyNumber(_V4Base):
    value: str
    metric: str
    subject: str = ""
    source_url: str = ""


class Source(_V4Base):
    title: str
    url: str = ""
    tool: str = ""
    reliability: SourceReliability = "medium"


# ---------------------------------------------------------------------------
# FinalReport — extended with bibliography and coverage metrics
# ---------------------------------------------------------------------------


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

    # --- structured output fields (Track A) ---
    qa_section: list[QAItem] = Field(default_factory=list)
    ranking: list[RankingItem] = Field(default_factory=list)
    tables: list[Table] = Field(default_factory=list)
    charts: list[ChartSpec] = Field(default_factory=list)
    callouts: list[CalloutBlock] = Field(default_factory=list)
    key_numbers_highlight: list[KeyNumberHighlight] = Field(default_factory=list)
    cover_image_prompt: str | None = None

    # --- v4.5 bibliography and citation coverage fields ---
    bibliography: list[NumberedSource] = Field(default_factory=list)
    citation_coverage: float = 0.0
    source_count: int = 0
    # main_synthesis stays as str for backward-compat; [REF:...] markers expected inline


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

    # v4.5: normalized intake results (optional, populated when Intake runs)
    normalized_reports: list[NormalizedReport] = Field(default_factory=list)


V4Session.model_rebuild()
FinalReport.model_rebuild()
AnalysisOutput.model_rebuild()
ExecutiveSummaryV4.model_rebuild()
