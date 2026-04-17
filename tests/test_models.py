"""Pydantic validation — schemas must reject bad data and accept valid data."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from smart_report.models import (
    Block,
    Cell,
    CrossLink,
    Finding,
    Matrix,
    Question,
    Report,
    ScoutTask,
)


def _sample_finding() -> Finding:
    return Finding(
        claim="Top-5 developers held 47% share.",
        number="47%",
        source_url="https://example.org/",
        source_type="official",
        verbatim_quote="цитата",
    )


def test_finding_rejects_unknown_source_type() -> None:
    with pytest.raises(ValidationError):
        Finding(
            claim="x",
            source_url="https://x",
            source_type="blog",  # type: ignore[arg-type]
        )


def test_finding_accepts_optional_fields_as_none() -> None:
    f = Finding(claim="x", source_url="https://x/", source_type="other")
    assert f.number is None
    assert f.verbatim_quote is None


def test_cell_requires_scout_task() -> None:
    with pytest.raises(ValidationError):
        Cell(id="a:b", domain="a", layer="b")  # type: ignore[call-arg]


def test_matrix_roundtrip() -> None:
    cell = Cell(
        id="market:structure",
        domain="market",
        layer="structure",
        scout_task=ScoutTask(cell_id="market:structure", query="q", target_sources=["Росстат"]),
    )
    m = Matrix(question_id="qid", domains=["market"], cells=[cell])
    assert m.model_dump()["cells"][0]["scout_task"]["query"] == "q"


def test_crosslink_type_literal() -> None:
    with pytest.raises(ValidationError):
        CrossLink(
            cell_a="a",
            cell_b="b",
            shared_variable="x",
            type="random",  # type: ignore[arg-type]
            insight="i",
        )


def test_report_full_shape() -> None:
    cell = Cell(
        id="c",
        domain="d",
        layer="l",
        scout_task=ScoutTask(cell_id="c", query="q"),
    )
    block = Block(
        cell_id="c",
        conclusion="C",
        findings=[_sample_finding()],
    )
    report = Report(
        question=Question(text="Q", id="qid"),
        matrix=Matrix(question_id="qid", domains=["d"], cells=[cell]),
        blocks=[block],
        cross_links=[],
        metadata={"k": "v"},
    )
    d = report.model_dump()
    assert d["question"]["id"] == "qid"
    assert d["blocks"][0]["findings"][0]["source_type"] == "official"


def test_extra_fields_are_forbidden() -> None:
    with pytest.raises(ValidationError):
        Question(text="q", id="i", extra_field="nope")  # type: ignore[call-arg]
