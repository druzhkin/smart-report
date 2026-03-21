from enum import Enum

from pydantic import BaseModel, Field


class QAVerdict(str, Enum):
    PASS = "PASS"
    REVISE = "REVISE"
    REJECT = "REJECT"


class QAIssue(BaseModel):
    category: str = Field(..., description="factual, logical, stylistic, citation, completeness")
    severity: str = Field(..., description="critical, major, minor")
    location: str
    description: str
    suggestion: str
    priority: int = Field(default=0, description="0=highest priority")


VISUAL_RUBRIC: dict[str, str] = {
    "structure": "Logical section flow, proper hierarchy, TOC-ready",
    "readability": "Clear language, appropriate length, no jargon overload",
    "formatting": "Consistent style, proper headings, bullet alignment",
    "charts": "Charts present, labelled, high-res, relevant to narrative",
    "executive_summary": "Concise, actionable, compelling, under 300 words",
}

SUBSTANCE_RUBRIC: dict[str, str] = {
    "factual_accuracy": "All claims verifiable against cited sources",
    "logical_coherence": "Argument flows without contradictions or gaps",
    "citation_quality": "Sources credible, recent, properly referenced",
    "completeness": "All key aspects of the topic covered",
    "actionability": "Recommendations specific, implementable, prioritized",
}


class QAResult(BaseModel):
    verdict: QAVerdict = QAVerdict.REVISE
    passed: bool = False
    overall_score: float = Field(ge=0.0, le=1.0)
    issues: list[QAIssue] = Field(default_factory=list)
    substance_score: float = Field(ge=0.0, le=1.0, default=0.0)
    visual_score: float = Field(ge=0.0, le=1.0, default=0.0)
    citation_score: float = Field(ge=0.0, le=1.0, default=0.0)
    revision_instructions: list[str] = Field(default_factory=list)
