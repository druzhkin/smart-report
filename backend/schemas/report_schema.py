from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field
import uuid


class ReportStatus(str, Enum):
    PENDING = "pending"
    INTAKE = "intake"
    PROMPTING = "prompting"
    RESEARCHING = "researching"
    REFLECTING = "reflecting"
    RENDERING = "rendering"
    QA = "qa"
    COMPLETED = "completed"
    FAILED = "failed"


class ReportSection(BaseModel):
    title: str
    content: str
    order: int
    sources: list[str] = Field(default_factory=list)


class ReportOutput(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    executive_summary: str
    sections: list[ReportSection] = Field(default_factory=list)
    status: ReportStatus = ReportStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.utcnow)
    total_cost_usd: float = Field(default=0.0)
    metadata: dict = Field(default_factory=dict)
