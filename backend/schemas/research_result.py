from datetime import datetime
from urllib.parse import urlparse

from pydantic import BaseModel, Field, computed_field


class Source(BaseModel):
    url: str
    title: str
    snippet: str
    domain: str = ""
    relevance_score: float = Field(ge=0.0, le=1.0, default=0.5)
    accessed_at: datetime = Field(default_factory=datetime.utcnow)

    def model_post_init(self, __context: object) -> None:
        if not self.domain and self.url:
            try:
                self.domain = urlparse(self.url).netloc
            except Exception:
                self.domain = ""


class ResearchResult(BaseModel):
    query: str
    findings: list[str] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    gaps: list[str] = Field(default_factory=list)
    iteration: int = Field(default=1)


class QueryBatch(BaseModel):
    queries: list[str]
    mode: str = Field(description="parallel or sequential", default="parallel")
    rationale: str = ""


class ParallelBatches(BaseModel):
    batches: list[QueryBatch] = Field(default_factory=list)
    total_queries: int = 0
    strategy_rationale: str = ""


class ResearchTask(BaseModel):
    id: str
    question: str
    parent_id: str | None = None
    depends_on: list[str] = Field(default_factory=list)
    status: str = "pending"
    priority: int = 1
    rationale: str = ""
    source_strategy: str = "hybrid"
    evidence_required: list[str] = Field(default_factory=list)


class ResearchBranchState(BaseModel):
    task_id: str
    question: str
    status: str = "pending"  # pending|running|completed|needs_follow_up|blocked
    next_action: str = "deepen"  # deepen|widen|verify|hold|complete
    action_reason: str = ""
    contradiction_notes: list[str] = Field(default_factory=list)
    evidence_count: int = 0
    source_count: int = 0
    source_domains: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    gaps: list[str] = Field(default_factory=list)
    follow_up_queries: list[str] = Field(default_factory=list)
    source_strategy: str = "hybrid"
    last_iteration: int = 0


class ResearchHypothesis(BaseModel):
    id: str
    statement: str
    status: str = "open"
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    conflicting_evidence_ids: list[str] = Field(default_factory=list)


class EvidenceItem(BaseModel):
    id: str
    query_id: str
    claim: str
    source_url: str = ""
    source_title: str = ""
    snippet: str = ""
    domain: str = ""
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    verification_status: str = "unverified"
    tags: list[str] = Field(default_factory=list)


class TaskDecomposition(BaseModel):
    main_question: str
    subquestions: list[ResearchTask] = Field(default_factory=list)
    hypotheses: list[ResearchHypothesis] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)
