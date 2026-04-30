"""Premium, non-breaking export planning layer.

This package does not replace the existing v4 exporters. It defines an
opt-in contract for high-value client deliverables: a deep report, a separate
presentation deck, evidence appendices, and QA gates.
"""

from .document import assemble_premium_report_document
from .docx import render_premium_docx
from .pptx import render_premium_pptx
from .models import (
    PremiumAppendixSpec,
    PremiumAudience,
    PremiumBlockKind,
    PremiumDeckSlideSpec,
    PremiumDeliverableSpec,
    PremiumEvidenceRequirement,
    PremiumPreparedBlock,
    PremiumPreparedSection,
    PremiumReportDocument,
    PremiumReportPlan,
    PremiumReportType,
    PremiumSectionSpec,
    PremiumVisualSpec,
)
from .planner import build_premium_report_plan
from .readiness import PremiumReadiness, PremiumReadinessIssue, assess_premium_readiness

__all__ = [
    "PremiumAppendixSpec",
    "PremiumAudience",
    "PremiumBlockKind",
    "PremiumDeckSlideSpec",
    "PremiumDeliverableSpec",
    "PremiumEvidenceRequirement",
    "PremiumPreparedBlock",
    "PremiumPreparedSection",
    "PremiumReportDocument",
    "PremiumReportPlan",
    "PremiumReportType",
    "PremiumSectionSpec",
    "PremiumVisualSpec",
    "assemble_premium_report_document",
    "render_premium_docx",
    "render_premium_pptx",
    "PremiumReadiness",
    "PremiumReadinessIssue",
    "assess_premium_readiness",
    "build_premium_report_plan",
]
