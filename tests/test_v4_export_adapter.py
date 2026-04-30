"""Export adapter — FinalReport -> report dict -> file on disk.

For each of the seven formats, run the writer end-to-end on a synthetic
FinalReport and confirm a non-empty file lands on disk.
"""

from __future__ import annotations

import json

import pytest

from smart_report.exporters import (
    v4_to_report_dict,
    write_docx,
    write_gamma_pdf_stub,
    write_gamma_pptx_stub,
    write_json,
    write_md,
    write_onepager_html,
    write_pptx,
)
from smart_report.models import (
    ExecutiveSummaryV4,
    FinalReport,
    KeyNumber,
    Source,
)


def _stub_final_report() -> FinalReport:
    return FinalReport(
        session_id="test-session",
        question="What defines developer success in Moscow business real estate?",
        research_prompt_used="Analyse Moscow developers for 2024.",
        executive_summary=ExecutiveSummaryV4(
            main_answer=(
                "Product quality explains more of commercial success than brand or speed."
            ),
            ranking="Продукт > скорость > бренд",
            top_findings=[
                "Top-5 developers hold 47% of business-class launches.",
                "Mortgage share fell from 78% to 55% in 2024.",
            ],
            key_numbers=[
                KeyNumber(value="47%", metric="Top-5 share", subject="2024"),
                KeyNumber(value="55%", metric="mortgage share", subject="2024"),
            ],
            confidence_note="Medium confidence.",
            what_meta_adds="Resolved vendor-skew in mortgage-share figure.",
        ),
        main_synthesis="## Позиция\n\nПродукт > скорость > бренд.",
        consensus_section="Three sources agree on top-3 developers.",
        conflicts_section="Mortgage share 55% vs 68% — we pick 55%.",
        gaps_filled_section="Delivery delays remain open.",
        all_sources=[
            Source(title="ERZ 2024", url="https://erzrf.ru/", tool="perplexity", reliability="high"),
            Source(title="Knight Frank 2024", url="", tool="openai_dr", reliability="low"),
        ],
        metadata={"source_reports_count": 2},
    )


def test_adapter_shape():
    rd = v4_to_report_dict(_stub_final_report())
    assert rd["session_id"] == "test-session"
    assert rd["title"]
    assert rd["executive_summary"]["main_answer"]
    assert rd["executive_summary"]["ranking"] == "Продукт > скорость > бренд"
    assert len(rd["executive_summary"]["key_numbers"]) == 2
    # sections assembled from the 4 markdown fields — all non-empty in fixture
    headings = [s["heading"] for s in rd["sections"]]
    assert "Основной синтез" in headings
    assert "Консенсус источников" in headings
    assert len(rd["sources"]) == 2


def test_write_md(tmp_path):
    rd = v4_to_report_dict(_stub_final_report())
    p = write_md(tmp_path / "out.md", rd)
    assert p.exists()
    content = p.read_text(encoding="utf-8")
    assert "Резюме" in content
    assert "47%" in content
    assert "Продукт" in content
    assert "Метаданные" not in content
    assert "source_reports_count" not in content


def test_write_json(tmp_path):
    rd = v4_to_report_dict(_stub_final_report())
    p = write_json(tmp_path / "out.json", rd)
    assert p.exists()
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["session_id"] == "test-session"


def test_write_onepager_html(tmp_path):
    rd = v4_to_report_dict(_stub_final_report())
    p = write_onepager_html(tmp_path / "one.html", rd)
    assert p.exists()
    html = p.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in html
    assert "47%" in html
    # html-escaped Russian should round-trip
    assert "Продукт" in html
    assert "source_reports_count" not in html


def test_write_docx(tmp_path):
    pytest.importorskip("docx")
    rd = v4_to_report_dict(_stub_final_report())
    p = write_docx(tmp_path / "out.docx", rd)
    assert p.exists()
    assert p.stat().st_size > 1000  # docx zip overhead ~ 1KB


def test_write_pptx(tmp_path):
    pytest.importorskip("pptx")
    rd = v4_to_report_dict(_stub_final_report())
    p = write_pptx(tmp_path / "out.pptx", rd)
    assert p.exists()
    assert p.stat().st_size > 1000


def test_write_gamma_stubs(tmp_path):
    rd = v4_to_report_dict(_stub_final_report())
    pptx = write_gamma_pptx_stub(tmp_path / "gamma.pptx.json", rd)
    pdf = write_gamma_pdf_stub(tmp_path / "gamma.pdf.json", rd)
    for p in (pptx, pdf):
        data = json.loads(p.read_text(encoding="utf-8"))
        assert data["stub"] is True
        assert data["session_id"] == "test-session"
