"""Report page and exhibit planning.

The planner converts a final report into a reviewable page plan before render.
It catches the failure mode the user repeatedly flagged: pages that are only
text, only visuals, empty, or visually present but analytically weak.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .evidence_graph import EvidenceGraph, build_evidence_graph
from .models import AnalysisOutput, FinalReport

PageKind = Literal["cover", "narrative", "mixed", "exhibit", "appendix"]


class _PageBase(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PlannedPage(_PageBase):
    page_no: int
    kind: PageKind
    title: str
    purpose: str
    required_text_blocks: int = 0
    required_visual_blocks: int = 0
    source_note_required: bool = False
    evidence_node_ids: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)


class PagePlanSummary(_PageBase):
    page_count: int
    exhibit_pages: int
    mixed_pages: int
    text_only_pages: int
    pages_with_issues: int
    status: Literal["ready", "needs_work", "blocked"]


class PagePlan(_PageBase):
    summary: PagePlanSummary
    pages: list[PlannedPage]
    global_issues: list[str] = Field(default_factory=list)


def build_page_plan(
    report: FinalReport,
    *,
    analysis: AnalysisOutput | None = None,
    evidence_graph: EvidenceGraph | None = None,
) -> PagePlan:
    graph = evidence_graph or build_evidence_graph(report, analysis)
    nodes = graph.nodes
    page_no = 1
    pages: list[PlannedPage] = [
        PlannedPage(
            page_no=page_no,
            kind="cover",
            title=_short_title(report.question),
            purpose="Signal topic, client decision context, and publication-grade report identity.",
            required_text_blocks=2,
            required_visual_blocks=1,
        )
    ]
    page_no += 1

    pages.append(
        PlannedPage(
            page_no=page_no,
            kind="mixed",
            title="Executive answer and decision implications",
            purpose="Answer the question first, with key numbers and confidence limits.",
            required_text_blocks=3,
            required_visual_blocks=1,
            evidence_node_ids=[node.claim_id for node in nodes[:4]],
            source_note_required=True,
        )
    )
    page_no += 1

    pages.append(
        PlannedPage(
            page_no=page_no,
            kind="exhibit",
            title="Evidence map",
            purpose="Show which conclusions are supported, partial, or unsupported.",
            required_text_blocks=1,
            required_visual_blocks=2,
            evidence_node_ids=[node.claim_id for node in nodes],
            source_note_required=True,
        )
    )
    page_no += 1

    if analysis:
        if analysis.consensus:
            pages.append(
                PlannedPage(
                    page_no=page_no,
                    kind="mixed",
                    title="Consensus and market baseline",
                    purpose="Separate agreed evidence from inference.",
                    required_text_blocks=3,
                    required_visual_blocks=1,
                    evidence_node_ids=[node.claim_id for node in nodes if "consensus" in node.origin][:6],
                    source_note_required=True,
                )
            )
            page_no += 1
        if analysis.conflicts:
            pages.append(
                PlannedPage(
                    page_no=page_no,
                    kind="mixed",
                    title="Contradictions and adjudication",
                    purpose="Explain conflicts, scope differences, and what evidence resolves them.",
                    required_text_blocks=3,
                    required_visual_blocks=1,
                    source_note_required=True,
                )
            )
            page_no += 1
        if analysis.gaps:
            pages.append(
                PlannedPage(
                    page_no=page_no,
                    kind="narrative",
                    title="Open gaps and follow-up requirements",
                    purpose="Make uncertainty explicit before recommendations.",
                    required_text_blocks=4,
                    required_visual_blocks=0,
                    source_note_required=False,
                )
            )
            page_no += 1

    for chart in report.charts[:4]:
        pages.append(
            PlannedPage(
                page_no=page_no,
                kind="exhibit",
                title=chart.title,
                purpose=chart.caption or "Use visual evidence to support or qualify a central claim.",
                required_text_blocks=1,
                required_visual_blocks=1,
                source_note_required=True,
            )
        )
        page_no += 1

    if report.tables:
        pages.append(
            PlannedPage(
                page_no=page_no,
                kind="exhibit",
                title="Data table and assumptions",
                purpose="Expose source-backed numbers, definitions, and comparability limits.",
                required_text_blocks=1,
                required_visual_blocks=1,
                source_note_required=True,
            )
        )
        page_no += 1

    pages.extend(
        [
            PlannedPage(
                page_no=page_no,
                kind="mixed",
                title="Implications and scenarios",
                purpose="Translate evidence into base/upside/downside implications.",
                required_text_blocks=3,
                required_visual_blocks=1,
                source_note_required=True,
            ),
            PlannedPage(
                page_no=page_no + 1,
                kind="appendix",
                title="Sources and methodology",
                purpose="Make source basis auditable.",
                required_text_blocks=2,
                required_visual_blocks=1,
                source_note_required=True,
            ),
        ]
    )

    for page in pages:
        _annotate_page_issues(page, graph)

    global_issues = _global_issues(pages, graph, report)
    pages_with_issues = sum(1 for page in pages if page.issues)
    status: Literal["ready", "needs_work", "blocked"]
    if graph.summary.unsupported or any("blocked" in issue.lower() for issue in global_issues):
        status = "blocked"
    elif pages_with_issues or global_issues:
        status = "needs_work"
    else:
        status = "ready"
    return PagePlan(
        summary=PagePlanSummary(
            page_count=len(pages),
            exhibit_pages=sum(1 for page in pages if page.kind == "exhibit"),
            mixed_pages=sum(1 for page in pages if page.kind == "mixed"),
            text_only_pages=sum(1 for page in pages if page.required_visual_blocks == 0),
            pages_with_issues=pages_with_issues,
            status=status,
        ),
        pages=pages,
        global_issues=global_issues,
    )


def _annotate_page_issues(page: PlannedPage, graph: EvidenceGraph) -> None:
    if page.required_text_blocks == 0 and page.required_visual_blocks == 0:
        page.issues.append("Page has no planned text or visual block.")
    if page.kind == "exhibit" and not page.source_note_required:
        page.issues.append("Exhibit page must carry source notes.")
    if page.kind == "narrative" and page.required_visual_blocks == 0 and page.required_text_blocks > 4:
        page.issues.append("Narrative page risks becoming a text dump; add a visual or callout.")
    if page.evidence_node_ids:
        by_id = {node.claim_id: node for node in graph.nodes}
        unsupported = [
            node_id
            for node_id in page.evidence_node_ids
            if by_id.get(node_id) and by_id[node_id].status == "unsupported"
        ]
        if unsupported:
            page.issues.append("Page includes unsupported claim(s): " + ", ".join(unsupported[:5]))


def _global_issues(pages: list[PlannedPage], graph: EvidenceGraph, report: FinalReport) -> list[str]:
    issues: list[str] = []
    if len(pages) < 10:
        issues.append("Report plan is shorter than 10 pages; full premium mode needs deeper pacing.")
    if sum(1 for page in pages if page.kind == "exhibit") < 4:
        issues.append("Too few exhibit pages; add source-backed charts/tables.")
    if graph.summary.unsupported:
        issues.append(f"Blocked: {graph.summary.unsupported} unsupported client-facing claim(s).")
    if not report.charts and not report.tables:
        issues.append("No chart/table specs found in final report.")
    return issues


def _short_title(question: str) -> str:
    clean = " ".join(str(question or "Report").split())
    return clean[:92] + ("..." if len(clean) > 92 else "")
