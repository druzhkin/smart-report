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
