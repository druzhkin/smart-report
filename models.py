"""Pydantic contracts for every hand-off between agents."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

SourceType = Literal[
    "primary_academic",
    "primary_official",
    "primary_data",
    "secondary",
    "opinion",
]
SearchType = Literal["web", "academic", "both"]


class Layer(BaseModel):
    name: str
    description: str = Field(..., description="What specifically to look for in this layer")


class ScoutTask(BaseModel):
    cell: str = Field(..., description="'Domain / Layer'")
    query_focus: str = Field(..., description="Concrete search assignment, not abstract")
    source_hints: str = Field(..., description="Preferred source types / organisations / years")
    search_type: SearchType = Field(
        default="both",
        description="Where Scout should look: 'web' | 'academic' | 'both'",
    )


class CellPlan(BaseModel):
    cell: str
    tasks: list[ScoutTask]


class Domain(BaseModel):
    name: str
    rationale: str = Field(..., description="Why this domain matters for the goal")
    layers: list[Layer]


QuestionType = Literal[
    "factual",
    "predictive",
    "comparative",
    "causal",
    "normative",
    "exploratory",
]


class Matrix(BaseModel):
    goal: str
    domains: list[Domain]
    cell_plans: list[CellPlan] = Field(
        default_factory=list,
        description="Per-cell scout task bundles. Cell = 'Domain / Layer'",
    )
    question_type: QuestionType = Field(
        default="exploratory",
        description="Classification of the user's question, set by planner",
    )


BiasType = Literal["vendor", "aggregation", "validated", "opinion"]


class Finding(BaseModel):
    claim: str
    source: str = Field(..., description="URL or DOI")
    source_label: str = Field(
        default="",
        description="Human-readable label — «Nature, 2024» or «Росстат, 2025»",
    )
    source_type: SourceType = Field(
        default="secondary",
        description=(
            "primary_academic | primary_official | primary_data | secondary | opinion"
        ),
    )
    citation_count: int | None = None
    year: int | None = None
    source_db: str | None = Field(
        default=None,
        description="'openalex'|'crossref'|'semantic_scholar'|'arxiv'|'pubmed'|'europe_pmc'|'doaj'|'core'|'perplexity'|'firecrawl'|'ddg'",
    )
    has_numbers: bool = False
    entities: list[str] = Field(default_factory=list)
    numeric_values: list[str] = Field(
        default_factory=list,
        description="Экстрактированные числа с единицами — '$2.4B', '15.7%', 'Q3 2024', 'n=1842'. Пусто если в claim нет цифр.",
    )
    verbatim_quote: str | None = Field(
        default=None,
        description="Дословная цитата из источника, подтверждающая claim. Обязательна если has_numbers=true.",
    )
    # Task 4 — source critique (optional)
    critique: str | None = None
    adjusted_range: str | None = None
    bias_type: BiasType | None = None


class Analogy(BaseModel):
    """Task 1 — structured historical analogy for a block."""
    situation: str
    expected: str
    actual: str
    why_diverged: str
    lesson: str
    location: str = Field(default="", description="City/country + year, e.g. 'London, 2012'")
    matched: list[str] = Field(default_factory=list, description="What specifically parallels the current finding")
    differed: list[str] = Field(default_factory=list, description="Key differences that change applicability")
    why_matters: str = Field(default="", description="Concrete implication for client decision")
    confidence: str = Field(default="moderate", description="high | moderate | speculative")


class IndicatorWarning(BaseModel):
    """Task 3 — observable signal for a competing hypothesis."""
    hypothesis: str
    indicator: str
    where_to_look: str
    timeframe: str = "6-12 месяцев"


class PreMortem(BaseModel):
    """Task 2 — pre-mortem: why the conclusion could be wrong."""
    failure_mode: str = Field(..., description="Как именно вывод может оказаться ошибочным")
    probability: str = Field(..., description="low | medium | high")
    early_signal: str = Field(..., description="Первый наблюдаемый знак, что всё идёт не так")
    mitigation: str = Field(..., description="Что сделать, чтобы застраховаться")


class ChainLink(BaseModel):
    cause: str
    effect: str
    mechanism: str = Field(..., description="Почему cause приводит к effect")
    evidence: str | None = Field(default=None, description="Якорь-тезис/источник")


class CausalChain(BaseModel):
    """Task 5 — long causal chain (4+ links across domains)."""
    title: str
    domains: list[str]
    links: list[ChainLink]
    terminal_implication: str = Field(..., description="Что из всей цепочки следует")
    confidence: str = Field(default="speculative", description="strong | moderate | speculative")


class ScoutResult(BaseModel):
    task: ScoutTask
    findings: list[Finding]
    notes: str | None = None


class QuantMetric(BaseModel):
    """Structured numeric metric extracted per cell before the Analyst runs.

    Decoupled from Finding so the Analyst can reference clean, normalized numbers
    without re-parsing free-text. `value` is a string to preserve units, ranges,
    and non-numeric qualifiers («~15%», «8–12», «<0.05»).
    """
    name: str = Field(..., description="Что измеряется — «премия за близость школы», «средний чек», «CTR»")
    value: str = Field(..., description="Значение с единицей — «15.7%», «$2.4B», «n=1842», «3–7%»")
    unit: str = Field(default="", description="%, USD, RUB, count, x, ratio, year, …")
    context: str = Field(..., description="1–2 предложения вокруг метрики из источника, дословно")
    confidence: str = Field(default="medium", description="high | medium | low")
    bias_type: BiasType = Field(default="opinion")
    source_url: str
    source_title: str = ""


class CorpusManifest(BaseModel):
    """Metadata about a corpus-flow fetch. Saved alongside raw corpus dump when
    save_raw_corpus=True so debugging / replay can reason about what went in.
    """
    goal: str
    fetched_at: str = Field(..., description="ISO-8601 timestamp")
    backends: list[str] = Field(default_factory=list, description="Which DR backends contributed")
    total_findings: int = 0
    by_backend: dict[str, int] = Field(
        default_factory=dict,
        description="findings-per-backend counts",
    )
    cost_usd: float = 0.0
    duration_sec: float = 0.0


class Block(BaseModel):
    cell: str
    summary: str = Field(..., description="Structured mini-report, not a list of facts")
    findings: list[Finding]
    gaps: list[str]
    key_entities: list[str]
    assumptions: list[str]
    analogies: list[Analogy] = Field(default_factory=list)
    indicators: list[IndicatorWarning] = Field(default_factory=list)
    decision_point: str | None = Field(
        default=None,
        description="Task 3 — ключевая развилка / решение, перед которым стоит читатель",
    )
    unverified_numerics: list[str] = Field(
        default_factory=list,
        description=(
            "Числа из summary, которые не удалось сопоставить ни с одним finding "
            "через fuzzy-матчинг. UI помечает их знаком ∑ как «синтезированные»."
        ),
    )
    quant_metrics: list[QuantMetric] = Field(
        default_factory=list,
        description="Structured numeric metrics extracted for this cell before analysis",
    )
    contrarian_critique: list[str] = Field(
        default_factory=list,
        description="Weaknesses / counter-evidence produced by the Contrarian Pass agent",
    )
    strongest_point: str | None = Field(
        default=None,
        description="Single sentence: what in this block would be hardest to refute",
    )


class Connection(BaseModel):
    domains: list[str]
    shared_entity: str
    nature: str = Field(..., description="paradox / shared_variable / causal_chain / unexpected_confirmation")
    description: str
    strength: str = Field(..., description="strong / moderate / speculative")
    anchors: list[str] = Field(
        default_factory=list,
        description="Цитируемые тезисы/цифры из блоков, на которых держится связь",
    )
    novelty: str | None = Field(
        default=None,
        description="Что нового даёт связь: вывод, не видимый из каждого блока по отдельности",
    )


class BlockHeader(BaseModel):
    cell: str
    one_liner: str = Field(..., description="Главный вывод блока в одном предложении")
    strongest_number: str = Field(..., description="Самая сильная цифра/факт с источником")
    main_gap: str = Field(..., description="Главный пробел блока")
    priority: str = Field(..., description="high | medium | low")
    score_novelty: int = 0
    score_concreteness: int = 0
    score_applicability: int = 0


class TopFinding(BaseModel):
    headline: str
    block_cell: str


class TopConnection(BaseModel):
    headline: str
    domains: list[str] = Field(default_factory=list)


class ExecutiveSummary(BaseModel):
    goal_restate: str
    matrix_table_md: str = Field(..., description="Компактная markdown-таблица домен × слои")
    top_findings: list[TopFinding]
    top_connections: list[TopConnection]
    key_gaps: list[str]


class Scenario(BaseModel):
    name: str  # "Base case" | "Optimistic" | "Pessimistic"
    probability: str  # e.g. "50-60%"
    description: str
    key_driver: str = Field(..., description="What must happen for this scenario")
    implications: list[str] = Field(default_factory=list, description="For the client, this means ...")
    indicators: list[str] = Field(default_factory=list, description="Observable signals linked to I&W")


class WildCard(BaseModel):
    description: str
    probability: str  # e.g. "<5%"
    impact: str


class ScenarioCone(BaseModel):
    question_horizon: str = Field(default="12-24 месяцев")
    key_uncertainties: list[str] = Field(default_factory=list)
    scenarios: list[Scenario]  # expected length 3
    wild_card: WildCard | None = None
    conditional_verdict: str = Field(default="", description="«При базовом сценарии (P=X)... при оптимистичном... ключевая развилка — ...»")


class AssumptionInversion(BaseModel):
    assumption: str
    inversion: str = Field(..., description="Что если допущение ЛОЖНО?")
    consequence: str = Field(..., description="Как изменится главный вывод блока, если допущение ложно")
    probability: str = Field(..., description="low | medium | high")
    early_signal: str = Field(..., description="Первый наблюдаемый сигнал, что допущение ложно")
    dependency: str = Field(..., description="critical | important | minor — если critical, вывод блока переворачивается")


class BlockInversions(BaseModel):
    block_cell: str
    inversions: list[AssumptionInversion]
    unfalsifiable_flag: bool = Field(default=False, description="True если ни одно допущение не critical — вывод нефальсифицируем")


class ConsensusAgreement(BaseModel):
    """One claim where ≥2 DR backends converged. Higher backend_count = higher confidence."""
    claim: str
    backends: list[str] = Field(default_factory=list, description="Which backends asserted this")
    backend_count: int = 0
    evidence: list[str] = Field(default_factory=list, description="Short paraphrases from each backend")
    confidence: str = Field(default="medium", description="high | medium | low")


class ConsensusDisagreement(BaseModel):
    """A topic where DR backends diverge. Each per-backend position must be preserved."""
    topic: str
    positions: list[dict] = Field(
        default_factory=list,
        description="[{backend, position, evidence_summary}, …]",
    )
    likely_resolution: str = Field(
        default="",
        description="Which backend is probably right and why (methodological / source-quality)",
    )


class ConsensusLayer(BaseModel):
    """Premium-only: meta-analysis across multiple DR backends' synth reports."""
    agreements: list[ConsensusAgreement] = Field(default_factory=list)
    disagreements: list[ConsensusDisagreement] = Field(default_factory=list)
    verdict: str = Field(
        default="",
        description="One-paragraph calibrated conclusion across all backends",
    )
    overall_confidence: str = Field(default="medium", description="high | medium | low")
    backends_consulted: list[str] = Field(default_factory=list)


class IntakeMessage(BaseModel):
    role: Literal["assistant", "user"]
    content: str


class IntakeContext(BaseModel):
    goal_original: str
    goal_enriched: str | None = None
    tier_proposed: str | None = None
    tier_chosen: str | None = None
    rationale: str | None = None
    messages: list[IntakeMessage] = []


class Report(BaseModel):
    goal: str
    matrix: Matrix
    blocks: list[Block]
    connections: list[Connection]
    exec_summary: ExecutiveSummary | None = None
    block_headers: list[BlockHeader] = Field(default_factory=list)
    pre_mortems: list[PreMortem] = Field(default_factory=list)
    causal_chains: list[CausalChain] = Field(default_factory=list)
    scenario_cone: ScenarioCone | None = None  # Cone of Plausibility — generated for predictive questions
    assumption_inversions: list[BlockInversions] = Field(default_factory=list)  # Quadrant Crunch — CIA SAT
    consensus_layer: ConsensusLayer | None = None  # Premium-only cross-backend meta-analysis
    intake_context: IntakeContext | None = None
