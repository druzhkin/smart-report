from enum import Enum

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Citation Verification
# ---------------------------------------------------------------------------

class CitationStatus(str, Enum):
    VERIFIED = "VERIFIED"
    PARTIAL = "PARTIAL"
    FABRICATED = "FABRICATED"
    DEAD_LINK = "DEAD_LINK"


class CitationCheckResult(BaseModel):
    url: str
    claim: str = ""
    status: CitationStatus
    similarity_score: float = Field(ge=0.0, le=1.0, default=0.0)
    page_title: str = ""
    error: str = ""


class CitationVerificationResult(BaseModel):
    checks: list[CitationCheckResult] = Field(default_factory=list)
    total: int = 0
    verified_count: int = 0
    partial_count: int = 0
    fabricated_count: int = 0
    dead_count: int = 0
    pass_rate: float = Field(ge=0.0, le=1.0, default=1.0)
    passed: bool = True

    def compute_stats(self) -> None:
        self.total = len(self.checks)
        self.verified_count = sum(1 for c in self.checks if c.status == CitationStatus.VERIFIED)
        self.partial_count = sum(1 for c in self.checks if c.status == CitationStatus.PARTIAL)
        self.fabricated_count = sum(
            1 for c in self.checks if c.status == CitationStatus.FABRICATED
        )
        self.dead_count = sum(1 for c in self.checks if c.status == CitationStatus.DEAD_LINK)
        non_fabricated = self.total - self.fabricated_count
        self.pass_rate = non_fabricated / self.total if self.total > 0 else 1.0
        self.passed = self.pass_rate >= 0.85


# ---------------------------------------------------------------------------
# Reflect
# ---------------------------------------------------------------------------

class ReflectIssue(BaseModel):
    description: str
    severity: str = Field(description="critical / major / minor", default="major")
    section: str = ""


class ReflectResult(BaseModel):
    issues: list[ReflectIssue] = Field(default_factory=list)
    additional_queries: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    quality_score: float = Field(ge=0.0, le=1.0, default=0.5)
    needs_more_research: bool = False


# ---------------------------------------------------------------------------
# Research Critique
# ---------------------------------------------------------------------------

class CritiqueScore(BaseModel):
    factual_accuracy: float = Field(ge=0.0, le=1.0, default=0.5)
    coverage: float = Field(ge=0.0, le=1.0, default=0.5)
    logic: float = Field(ge=0.0, le=1.0, default=0.5)
    depth: float = Field(ge=0.0, le=1.0, default=0.5)
    sources: float = Field(ge=0.0, le=1.0, default=0.5)


class ResearchCritiqueResult(BaseModel):
    verdict: str = Field(description="ACCEPT or REVISE", default="ACCEPT")
    scores: CritiqueScore = Field(default_factory=CritiqueScore)
    overall_score: float = Field(ge=0.0, le=1.0, default=0.5)
    blocking_issues: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    challenged_claims: list[dict] = Field(default_factory=list)
