"""Tests for smart_report.exporters.chart_renderer.

Each test:
  1. Loads a fixture from tests/fixtures/chart_samples/<type>.json
  2. Builds a ChartSpec and renders to runs/night_upgrade/chart_samples/
  3. Asserts the PNG exists, 1 KB < size < 1 MB, and PIL can open it
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from smart_report.exporters.chart_renderer import ChartSpec, render_chart

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "chart_samples"
OUTPUT_DIR = (
    Path(__file__).parent.parent
    / "runs"
    / "night_upgrade"
    / "chart_samples"
)


def _load_spec(chart_type: str) -> ChartSpec:
    """Load fixture JSON and construct a ChartSpec."""
    path = FIXTURE_DIR / f"{chart_type}.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    return ChartSpec(
        chart_type=raw["chart_type"],
        title=raw["title"],
        data=raw["data"],
        x_label=raw.get("x_label"),
        y_label=raw.get("y_label"),
        caption=raw.get("caption"),
    )


def _assert_png(path: Path) -> None:
    """Assert path is a readable PNG between 1 KB and 1 MB."""
    assert path.exists(), f"PNG not created: {path}"
    size = path.stat().st_size
    assert size > 1_024, f"PNG too small ({size} bytes): {path}"
    assert size < 1_048_576, f"PNG too large ({size} bytes): {path}"
    img = Image.open(path)
    img.verify()  # raises if not valid image


# ---------------------------------------------------------------------------
# Test cases — one per chart_type
# ---------------------------------------------------------------------------

class TestBarChart:
    def test_renders_bar_chart(self, tmp_path):
        spec = _load_spec("bar")
        out = OUTPUT_DIR / "bar.png"
        result = render_chart(spec, out)
        _assert_png(result)

    def test_bar_chart_to_tmp(self, tmp_path):
        spec = _load_spec("bar")
        out = tmp_path / "bar.png"
        result = render_chart(spec, out)
        _assert_png(result)
        img = Image.open(result)
        # 8x5 @150 DPI → 1200x750 pixels (±some margin)
        assert img.width >= 800
        assert img.height >= 500


class TestLineChart:
    def test_renders_line_chart(self, tmp_path):
        spec = _load_spec("line")
        out = OUTPUT_DIR / "line.png"
        result = render_chart(spec, out)
        _assert_png(result)

    def test_line_chart_multi_series(self, tmp_path):
        """Two series should both render without error."""
        spec = _load_spec("line")
        assert len(spec.data["series"]) == 2
        out = tmp_path / "line_multi.png"
        result = render_chart(spec, out)
        _assert_png(result)


class TestPieChart:
    def test_renders_pie_donut(self, tmp_path):
        spec = _load_spec("pie")
        out = OUTPUT_DIR / "pie.png"
        result = render_chart(spec, out)
        _assert_png(result)

    def test_pie_center_text_present(self, tmp_path):
        """Pie fixture includes center_text — should not raise."""
        spec = _load_spec("pie")
        assert spec.data.get("center_text") is not None
        out = tmp_path / "pie_center.png"
        result = render_chart(spec, out)
        _assert_png(result)


class TestStackedBarChart:
    def test_renders_stacked_bar(self, tmp_path):
        spec = _load_spec("stacked_bar")
        out = OUTPUT_DIR / "stacked_bar.png"
        result = render_chart(spec, out)
        _assert_png(result)

    def test_stacked_bar_two_series(self, tmp_path):
        spec = _load_spec("stacked_bar")
        assert len(spec.data["series"]) == 2
        out = tmp_path / "stacked_bar_two.png"
        result = render_chart(spec, out)
        _assert_png(result)


class TestWaterfallChart:
    def test_renders_waterfall(self, tmp_path):
        spec = _load_spec("waterfall")
        out = OUTPUT_DIR / "waterfall.png"
        result = render_chart(spec, out)
        _assert_png(result)

    def test_waterfall_types_array(self, tmp_path):
        spec = _load_spec("waterfall")
        types = spec.data.get("types", [])
        assert "base" in types
        assert "negative" in types
        assert "total" in types
        out = tmp_path / "waterfall_types.png"
        result = render_chart(spec, out)
        _assert_png(result)


class TestScatterChart:
    def test_renders_scatter(self, tmp_path):
        spec = _load_spec("scatter")
        out = OUTPUT_DIR / "scatter.png"
        result = render_chart(spec, out)
        _assert_png(result)

    def test_scatter_multi_series(self, tmp_path):
        spec = _load_spec("scatter")
        assert len(spec.data["series"]) == 2
        out = tmp_path / "scatter_multi.png"
        result = render_chart(spec, out)
        _assert_png(result)


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestErrors:
    def test_unknown_chart_type_raises(self, tmp_path):
        spec = ChartSpec(
            chart_type="bar",  # valid type for construction
            title="Test",
            data={"labels": ["A"], "values": [1]},
        )
        # Monkey-patch to invalid type to test dispatch guard
        spec.chart_type = "radar"  # type: ignore[assignment]
        with pytest.raises(ValueError, match="Unsupported chart_type"):
            render_chart(spec, tmp_path / "out.png")

    def test_output_dir_is_created(self, tmp_path):
        """render_chart must create missing parent directories."""
        spec = _load_spec("bar")
        nested = tmp_path / "deep" / "nested" / "bar.png"
        result = render_chart(spec, nested)
        _assert_png(result)
