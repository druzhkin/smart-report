"""Manual visual review contract for premium delivery artifacts.

Automated render QA can prove that DOCX/PPTX files open and render. It cannot
honestly prove that typography, table breaks, hierarchy, and polish are good
enough for paid delivery. This module creates an explicit manual-review gate
that can be approved later by a human reviewer or UI workflow.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

VisualReviewStatus = Literal["approved", "pending", "blocked"]


class _VisualReviewBase(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class VisualReviewItem(_VisualReviewBase):
    id: str
    label: str
    status: VisualReviewStatus = "pending"
    notes: str = ""


class VisualReviewReport(_VisualReviewBase):
    ready: bool
    status: VisualReviewStatus
    render_index: str = ""
    items: list[VisualReviewItem] = Field(default_factory=list)
    summary: str


VISUAL_REVIEW_ITEMS = (
    ("overflow", "No text overflow, clipping, or overlapping elements."),
    ("tables", "Tables are readable without broken rows, orphan headers, or cramped cells."),
    ("hierarchy", "Headings create a clear executive-to-detail hierarchy."),
    ("breaks", "Page and slide breaks preserve complete ideas and do not strand captions."),
    ("visuals", "Charts, scorecards, and badges are visually aligned and easy to scan."),
    ("polish", "The package looks like a finished paid report, not a raw model export."),
)


def build_visual_review_gate(
    artifact_qa: dict,
    *,
    approved: bool = False,
    reviewer_notes: dict[str, str] | None = None,
) -> VisualReviewReport:
    """Build the visual review gate from rendered artifact QA output."""

    reviewer_notes = reviewer_notes or {}
    render_index = str(artifact_qa.get("render_index") or "")
    artifact_status = artifact_qa.get("status")
    if artifact_status != "passed" or not render_index:
        return VisualReviewReport(
            ready=False,
            status="blocked",
            render_index=render_index,
            items=[
                VisualReviewItem(id=item_id, label=label, status="blocked")
                for item_id, label in VISUAL_REVIEW_ITEMS
            ],
            summary="Manual visual review is blocked until rendered artifact QA passes.",
        )

    status: VisualReviewStatus = "approved" if approved else "pending"
    items = [
        VisualReviewItem(
            id=item_id,
            label=label,
            status=status,
            notes=reviewer_notes.get(item_id, ""),
        )
        for item_id, label in VISUAL_REVIEW_ITEMS
    ]
    return VisualReviewReport(
        ready=approved,
        status=status,
        render_index=render_index,
        items=items,
        summary=(
            "Manual visual review approved."
            if approved
            else "Manual visual review is pending; inspect the rendered index before client delivery."
        ),
    )
