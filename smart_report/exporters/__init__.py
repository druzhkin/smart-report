"""v4 exporters. Adapter turns FinalReport into a uniform dict, per-format
renderers consume that dict and write files.

Public entry points:

    v4_to_report_dict(final)    -> dict          (adapter)
    render_markdown(rd)         -> str
    write_md(path, rd) / write_json(path, rd)
    write_onepager_html(path, rd)
    write_docx(path, rd)        requires python-docx
    write_pptx(path, rd)        requires python-pptx
    gamma_pptx_stub(path, rd) / gamma_pdf_stub(path, rd)
"""

from __future__ import annotations

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
]
