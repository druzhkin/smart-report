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
from typing import Optional

from .v4_to_report import v4_to_report_dict
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
from .docx_v4_consulting import render_consulting_docx
from .docx_js_bridge import (
    render_docx_js,
    is_node_available,
    NodeNotFoundError,
    NodeRenderError,
)

logger = logging.getLogger(__name__)


def render_docx(
    report,
    path: Path,
    chart_dir: Optional[Path] = None,
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
    "render_docx",
    "is_node_available",
    "NodeNotFoundError",
    "NodeRenderError",
]
