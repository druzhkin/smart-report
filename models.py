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


class Matrix(BaseModel):
    goal: str
    domains: list[Domain]
    cell_plans: list[CellPlan] = Field(
        default_factory=list,
        description="Per-cell scout task bundles. Cell = 'Domain / Layer'",
    )


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


class ScoutResult(BaseModel):
    task: ScoutTask
    findings: list[Finding]
    notes: str | None = None


class Block(BaseModel):
    cell: str
    summary: str = Field(..., description="Structured mini-report, not a list of facts")
    findings: list[Finding]
    gaps: list[str]
    key_entities: list[str]
    assumptions: list[str]


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


class Report(BaseModel):
    goal: str
    matrix: Matrix
    blocks: list[Block]
    connections: list[Connection]
    exec_summary: ExecutiveSummary | None = None
    block_headers: list[BlockHeader] = Field(default_factory=list)
    budget_exhausted: bool = False
    budget_note: str | None = None
