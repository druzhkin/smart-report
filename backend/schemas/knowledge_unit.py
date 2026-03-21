from datetime import datetime
from pydantic import BaseModel, Field


class KnowledgeUnit(BaseModel):
    id: str
    content: str
    source: str
    category: str = Field(..., description="fact, statistic, definition, quote, methodology")
    confidence: float = Field(ge=0.0, le=1.0, default=0.8)
    tags: list[str] = Field(default_factory=list)
    source_url: str = ""
    verification_status: str = "VERIFIED"
    created_at: datetime = Field(default_factory=datetime.utcnow)


class LibraryHit(BaseModel):
    report_id: str
    title: str
    similarity: float = Field(ge=0.0, le=1.0)
    summary: str = ""
    session_id: str = ""
    dataset_id: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SourceRecord(BaseModel):
    url: str
    title: str = ""
    domain: str = ""
    reliability_score: float = Field(ge=0.0, le=1.0, default=0.5)
    topic_tags: list[str] = Field(default_factory=list)
    document_id: str = ""
