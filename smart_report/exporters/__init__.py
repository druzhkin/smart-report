"""v4 exporters. Adapter turns FinalReport into a uniform dict, per-format
renderers consume that dict and write files.

Public entry points:

    v4_to_report_dict(final)    -> dict          (adapter)
    render_markdown(rd)         -> str
    write_md(path, rd) / write_json(path, rd)
    write_onepager_html(path, rd)
    write_docx(path, rd)        requires python-docx  (legacy renderer)
    write_pptx(path, rd)        requires python-pptx
    gamma_pptx_stub(path, rd) / gamma_pdf_stub(path, rd)

    render_consulting_docx(report, path, chart_dir=None)
                                Professional consulting DOCX (python-docx, Track B legacy)

    render_docx_js(report, path, chart_dir=None)
                                DOCX v2 renderer (Node.js + docx-js, navy/gold palette)

    render_docx(report, path, chart_dir=None)
                                Auto-selects: Node.js renderer if available,
                                falls back to python-docx renderer.

    is_node_available()         True if Node.js + node_modules ready
"""

from __future__ import annotations

import logging
from pathlib import Path

from .client_readiness import ClientReadiness, ReadinessIssue, assess_client_readiness
from .client_view import contains_client_leak, sanitize_final_report
from .docx_js_bridge import (
    NodeNotFoundError,
    NodeRenderError,
    is_node_available,
    render_docx_js,
)
from .docx_v4_consulting import render_consulting_docx
from .premium import (
    DEFAULT_REGENERATION_FORMATS,
    CarboneRenderError,
    PremiumAppendixSpec,
    PremiumAudience,
    PremiumBlockKind,
    PremiumDeckSlideSpec,
    PremiumDeliverableSpec,
    PremiumEvidenceRequirement,
    PremiumPreparedBlock,
    PremiumPreparedSection,
    PremiumPublicationSpec,
    PremiumReadiness,
    PremiumReadinessIssue,
    PremiumReportDocument,
    PremiumReportPlan,
    PremiumReportType,
    PremiumSectionSpec,
    PremiumVisualSpec,
    ReportActorRole,
    ReportArtifactFormat,
    ReportEditableField,
    ReportEditRequest,
    ReportQualityGateIssue,
    ReportQualityGateResult,
    ReportRegenerationPlan,
    ReportSourceMetadata,
    ReportVersionEntry,
    ResearchConnector,
    ResearchCoverage,
    StructuredReportBlock,
    StructuredReportSection,
    StructuredReportSource,
    StructuredReportSourceRef,
    StructuredReportVisual,
    apply_publication_remediation,
    apply_report_edits,
    assemble_premium_report_document,
    assess_premium_readiness,
    assess_premium_storyboard_quality,
    build_premium_report_plan,
    build_regeneration_plan,
    create_report_version,
    final_report_from_structured_source,
    hash_structured_source,
    list_editable_paths,
    render_premium_carbone_pdf,
    render_premium_docx,
    render_premium_pdf,
    render_premium_pptx,
    run_enterprise_quality_gates,
    structured_source_from_final_report,
    to_carbone_data,
)
from .render import (
    render_markdown,
    write_docx,
    write_gamma_pdf_stub,
    write_gamma_pptx_stub,
    write_json,
    write_md,
    write_onepager_html,
    write_pptx,
)
from .v4_to_report import v4_to_report_dict

logger = logging.getLogger(__name__)


def render_docx(
    report,
    path: Path,
    chart_dir: Path | None = None,
    *,
    prefer: str = "node",
) -> Path:
    """
    Auto-selecting DOCX renderer.

    Tries Node.js docx-js renderer first (if ``prefer="node"`` and Node is available),
    then falls back to python-docx consulting renderer.

    Parameters
    ----------
    report : FinalReport
    path : Path -- output .docx path
    chart_dir : Path or None -- pre-rendered chart PNGs directory
    prefer : "node" | "python" -- which renderer to try first

    Returns
    -------
    Path -- the written file path
    """
    if prefer == "node" and is_node_available():
        try:
            logger.info("Using Node.js docx-js renderer (v2)")
            return render_docx_js(report, path, chart_dir=chart_dir)
        except (NodeNotFoundError, NodeRenderError) as exc:
            logger.warning(
                "Node.js renderer failed (%s), falling back to python-docx: %s",
                type(exc).__name__,
                exc,
            )

    logger.info("Using python-docx renderer (legacy Track B)")
    return render_consulting_docx(report, path, chart_dir=chart_dir)


__all__ = [
    "v4_to_report_dict",
    "render_markdown",
    "write_docx",
    "write_gamma_pdf_stub",
    "write_gamma_pptx_stub",
    "write_json",
    "write_md",
    "write_onepager_html",
    "write_pptx",
    "render_consulting_docx",
    "render_docx_js",
    "ClientReadiness",
    "ReadinessIssue",
    "assess_client_readiness",
    "contains_client_leak",
    "render_docx",
    "sanitize_final_report",
    "is_node_available",
    "NodeNotFoundError",
    "NodeRenderError",
    "PremiumAppendixSpec",
    "PremiumAudience",
    "PremiumBlockKind",
    "PremiumDeckSlideSpec",
    "PremiumDeliverableSpec",
    "PremiumEvidenceRequirement",
    "PremiumPreparedBlock",
    "PremiumPreparedSection",
    "PremiumPublicationSpec",
    "PremiumReportDocument",
    "PremiumReportPlan",
    "PremiumReportType",
    "PremiumReadiness",
    "PremiumReadinessIssue",
    "PremiumSectionSpec",
    "PremiumVisualSpec",
    "DEFAULT_REGENERATION_FORMATS",
    "ReportActorRole",
    "ReportArtifactFormat",
    "ReportEditableField",
    "ReportEditRequest",
    "ReportQualityGateIssue",
    "ReportQualityGateResult",
    "ReportRegenerationPlan",
    "ReportSourceMetadata",
    "ReportVersionEntry",
    "ResearchConnector",
    "ResearchCoverage",
    "StructuredReportBlock",
    "StructuredReportSection",
    "StructuredReportSource",
    "StructuredReportSourceRef",
    "StructuredReportVisual",
    "CarboneRenderError",
    "apply_publication_remediation",
    "apply_report_edits",
    "assemble_premium_report_document",
    "assess_premium_readiness",
    "assess_premium_storyboard_quality",
    "build_premium_report_plan",
    "build_regeneration_plan",
    "create_report_version",
    "final_report_from_structured_source",
    "hash_structured_source",
    "list_editable_paths",
    "render_premium_carbone_pdf",
    "render_premium_docx",
    "render_premium_pdf",
    "render_premium_pptx",
    "run_enterprise_quality_gates",
    "structured_source_from_final_report",
    "to_carbone_data",
]
