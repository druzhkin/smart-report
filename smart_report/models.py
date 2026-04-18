"""Pydantic v2 schemas — the single source of truth for the pipeline."""

from __future__ import annotations

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
