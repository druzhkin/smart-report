"""Universal premium report planning models.

These models are intentionally domain-neutral. They describe what a paid,
client-ready research package should contain without hard-coding any topic
such as real estate, finance, technology, or law.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _PremiumBase(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


PremiumReportType = Literal[
    "market",
    "investment",
    "competitive",
    "strategy",
    "technical_audit",
    "legal_regulatory",
    "due_diligence",
    "general_research",
]

PremiumAudience = Literal[
    "buyer",
    "investor",
    "executive",
    "operator",
    "developer",
    "analyst",
    "technical_lead",
    "general_client",
]

PremiumBlockKind = Literal[
    "narrative",
    "kpi_grid",
    "evidence_table",
    "source_quality_table",
    "timeline",
    "scenario_matrix",
    "sensitivity_table",
    "decision_matrix",
    "risk_register",
    "market_map",
    "competitive_matrix",
    "methodology_box",
    "appendix_table",
    "chart",
]

PremiumPageType = Literal["cover", "section_opener", "thesis", "exhibit", "appendix"]

PremiumVisualType = Literal[
    "none",
    "narrative_text",
    "hero_kpi_strip",
    "ranking_bar",
    "time_series",
    "distribution",
    "scenario_matrix",
    "risk_heatmap",
    "evidence_quality",
    "waterfall",
    "market_map",
    "source_table",
]


class PremiumVisualSpec(_PremiumBase):
    """A required visual element in the premium report/deck."""

    kind: PremiumBlockKind
    title: str
    purpose: str
    min_count: int = Field(default=1, ge=1)


class PremiumSectionSpec(_PremiumBase):
    """A section the report must contain."""

    id: str
    title: str
    purpose: str
    min_pages: float = Field(default=1.0, ge=0.25)
    required_blocks: list[PremiumBlockKind] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _id_is_stable(cls, value: str) -> str:
        if not value.replace("_", "").replace("-", "").isalnum():
            raise ValueError("section id must be stable and slug-like")
        return value


class PremiumAppendixSpec(_PremiumBase):
    """Appendix requirement for a defensible paid report."""

    title: str
    purpose: str
    required: bool = True


class PremiumEvidenceRequirement(_PremiumBase):
    """Minimum evidence bar for premium delivery."""

    min_sources: int = Field(default=8, ge=0)
    min_authoritative_sources: int = Field(default=3, ge=0)
    min_numeric_facts: int = Field(default=20, ge=0)
    require_source_quality_table: bool = True
    require_fact_to_source_mapping: bool = True
    require_limitations_section: bool = True


class PremiumDeliverableSpec(_PremiumBase):
    """Expected final artifact set."""

    report_min_pages: int = Field(default=20, ge=1)
    deck_min_slides: int = Field(default=10, ge=1)
    require_pdf: bool = True
    require_docx: bool = True
    require_pptx: bool = True
    require_qa_audit: bool = True
    require_data_pack: bool = True


class PremiumPublicationSpec(_PremiumBase):
    """Publication-grade layout bar for consulting-style PDFs.

    This is separate from deliverable formats. A DOCX/PPTX/PDF package can exist
    and still fail the publication bar if it reads like a plain Word export.
    """

    reference_style: str = "consulting_publication"
    require_full_bleed_cover: bool = True
    require_image_led_section_openers: bool = True
    require_exhibit_pages: bool = True
    require_source_notes_on_exhibits: bool = True
    require_editorial_grid: bool = True
    require_visual_qa: bool = True
    min_exhibit_pages: int = Field(default=4, ge=0)
    min_data_dense_exhibits: int = Field(default=3, ge=0)


class PremiumReportPlan(_PremiumBase):
    """Domain-neutral plan for a high-value report package."""

    report_type: PremiumReportType
    audience: PremiumAudience
    decision_context: str
    quality_bar: str = "paid_client_10000_rub"
    deliverables: PremiumDeliverableSpec = Field(default_factory=PremiumDeliverableSpec)
    evidence: PremiumEvidenceRequirement = Field(default_factory=PremiumEvidenceRequirement)
    publication: PremiumPublicationSpec = Field(default_factory=PremiumPublicationSpec)
    sections: list[PremiumSectionSpec]
    required_visuals: list[PremiumVisualSpec]
    appendices: list[PremiumAppendixSpec]
    deck_outline: list[str]
    non_breaking_notes: list[str] = Field(default_factory=list)

    @field_validator("sections")
    @classmethod
    def _enforce_minimum_structure(
        cls, value: list[PremiumSectionSpec]
    ) -> list[PremiumSectionSpec]:
        if len(value) < 8:
            raise ValueError("premium report plan must contain at least 8 sections")
        return value

    @field_validator("deck_outline")
    @classmethod
    def _deck_has_enough_slides(cls, value: list[str]) -> list[str]:
        if len(value) < 8:
            raise ValueError("premium deck outline must contain at least 8 slides")
        return value


class PremiumPreparedBlock(_PremiumBase):
    """Concrete content block assembled from report/analysis data."""

    kind: PremiumBlockKind
    title: str
    body: str = ""
    columns: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class PremiumPreparedSection(_PremiumBase):
    """Concrete section ready for a renderer."""

    id: str
    title: str
    purpose: str
    min_pages: float
    blocks: list[PremiumPreparedBlock] = Field(default_factory=list)


class PremiumPageVisual(_PremiumBase):
    """A publication visual planned at page level, before rendering."""

    visual_type: PremiumVisualType
    title: str
    data: dict[str, Any] = Field(default_factory=dict)
    source_notes: list[str] = Field(default_factory=list)


class PremiumPage(_PremiumBase):
    """Storyboard page for publication-grade PDF rendering."""

    page_type: PremiumPageType
    thesis: str
    narrative: str = ""
    visual: PremiumPageVisual | None = None
    implication: str = ""
    source_notes: list[str] = Field(default_factory=list)


class PremiumDeckSlideSpec(_PremiumBase):
    """Separate presentation slide derived from the report, not a replacement."""

    title: str
    objective: str
    source_section_id: str | None = None
    suggested_blocks: list[PremiumBlockKind] = Field(default_factory=list)


class PremiumReportDocument(_PremiumBase):
    """Renderer-neutral premium document package."""

    title: str
    subtitle: str
    plan: PremiumReportPlan
    pages: list[PremiumPage] = Field(default_factory=list)
    sections: list[PremiumPreparedSection]
    appendices: list[PremiumPreparedSection]
    deck_slides: list[PremiumDeckSlideSpec]
    source_count: int = 0
    numeric_fact_count: int = 0
    premium_readiness: dict[str, object] | None = None
