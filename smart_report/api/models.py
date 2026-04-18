"""Request/response shapes for the API layer."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ResearchIn(BaseModel):
    question: str = Field(..., min_length=3, max_length=4000)
    dry_run: bool = False


class ResearchOut(BaseModel):
    id: str
    status: str


class JobSummary(BaseModel):
    id: str
    question: str
    status: str
    created_at: float
    finished_at: float | None = None
    error: str | None = None
