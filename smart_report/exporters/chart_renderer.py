"""Chart renderer — converts ChartSpec to PNG using matplotlib.

Editorial dark-paper aesthetic:
  - Figure 8×5 inches, DPI 150
  - Palette: amber accent #B8862E, neutrals #0A0A0A / #6B6B6B / #FAF9F6
  - No full grid; only horizontal axis lines
  - Top/right spines removed
  - Title: 16pt bold serif; axis labels: 11pt sans
  - Source attribution: micro-text bottom-left via fig.text(0.02, 0.02, ...)
  - Fonts: DejaVu Serif for display; DejaVu Sans (matplotlib default) for body

spec.data shape per chart_type
================================

bar
----
  data = {
      "labels": list[str],   # category names on X axis
      "values": list[float], # bar heights
  }
  Optional key: "source" (str) — overrides spec.caption in source attribution.

line
----
  data = {
      "series": [
          {
              "label": str,      # legend entry
              "x":     list[str | float],  # X positions (can be category strings)
              "y":     list[float],        # Y values
          },
          ...
      ]
  }

pie  (rendered as donut with optional centred big number)
----
  data = {
      "labels": list[str],
      "values": list[float],
      "center_text":  str | None,   # big number displayed in the donut hole
      "center_label": str | None,   # smaller label below center_text
  }

stacked_bar
-----------
  data = {
      "labels": list[str],   # category names on X axis
      "series": [
          {
              "label":  str,
              "values": list[float],
          },
          ...
      ]
  }

waterfall
---------
  data = {
      "labels": list[str],
      "values": list[float],  # positive = increase, negative = decrease
      "types":  list[str],    # one of: "base" | "positive" | "negative" | "total"
  }
  The renderer accumulates a running total; bars are coloured by type.

scatter
-------
  data = {
      "series": [
          {
              "label": str,
              "x":     list[float],
              "y":     list[float],
          },
          ...
      ]
  }
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import matplotlib
matplotlib.use("Agg")  # non-interactive backend; must come before pyplot import

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.ticker as ticker
import numpy as np

# ---------------------------------------------------------------------------
# Temporary mock ChartSpec — replace once Track A merges
# ---------------------------------------------------------------------------

# TODO: replace with smart_report.models.ChartSpec once Track A merges
@dataclass
class ChartSpec:
    """Mirrors smart_report.models.ChartSpec exactly (Track A contract)."""

    chart_type: Literal["bar", "line", "pie", "scatter", "stacked_bar", "waterfall"]
    title: str
    data: dict
    x_label: str | None = None
    y_label: str | None = None
    caption: str | None = None

    # Allow construction from the pydantic model transparently
    @classmethod
    def from_pydantic(cls, obj: object) -> "ChartSpec":
        """Convert a pydantic ChartSpec instance to this dataclass."""
        return cls(
            chart_type=obj.chart_type,  # type: ignore[attr-defined]
            title=obj.title,  # type: ignore[attr-defined]
            data=obj.data,  # type: ignore[attr-defined]
            x_label=getattr(obj, "x_label", None),
            y_label=getattr(obj, "y_label", None),
            caption=getattr(obj, "caption", None),
        )


# ---------------------------------------------------------------------------
# Palette & rcParams
# ---------------------------------------------------------------------------

AMBER = "#B8862E"
DARK = "#0A0A0A"
MID = "#6B6B6B"
LIGHT = "#FAF9F6"
WHITE = "#FFFFFF"

# A secondary palette for multi-series charts — amber first, then neutrals
_MULTI_PALETTE = [AMBER, "#5A5A5A", "#A0A0A0", "#C8A86E", "#3D3D3D", "#D4C4A0"]

_POSITIVE_COLOR = AMBER
_NEGATIVE_COLOR = MID
_TOTAL_COLOR = DARK
_BASE_COLOR = "#888888"

def _apply_rcparams() -> None:
    """Apply global rcParams for the editorial dark-paper aesthetic."""
    plt.rcParams.update(
        {
            "figure.facecolor": LIGHT,
            "axes.facecolor": LIGHT,
            "axes.edgecolor": MID,
            "axes.labelcolor": DARK,
            "axes.titlecolor": DARK,
            "text.color": DARK,
            "xtick.color": MID,
            "ytick.color": MID,
            "xtick.labelsize": 10,
            "ytick.labelsize": 10,
            "axes.labelsize": 11,
            "legend.fontsize": 10,
            "legend.frameon": False,
            "font.family": "serif",
            "font.serif": ["DejaVu Serif", "Georgia", "Times New Roman", "serif"],
            "font.sans-serif": ["DejaVu Sans", "Arial", "sans-serif"],
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "axes.grid.axis": "y",     # horizontal lines only
            "grid.color": "#D8D8D0",
            "grid.linewidth": 0.5,
            "grid.linestyle": "--",
            "savefig.facecolor": LIGHT,
            "savefig.dpi": 150,
            "figure.dpi": 150,
        }
    )


def _new_fig() -> tuple[plt.Figure, plt.Axes]:
    """Create a fresh 8×5 figure with a single axes."""
    _apply_rcparams()
    fig, ax = plt.subplots(figsize=(8, 5))
    return fig, ax


def _style_ax(ax: plt.Axes) -> None:
    """Remove top/right spines; ensure only Y-gridlines."""
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(MID)
    ax.spines["bottom"].set_color(MID)
    ax.yaxis.grid(True, color="#D8D8D0", linewidth=0.5, linestyle="--")
    ax.xaxis.grid(False)
    ax.set_axisbelow(True)


def _add_source(fig: plt.Figure, text: str) -> None:
    """Add micro-text source attribution at bottom-left."""
    fig.text(
        0.02,
        0.02,
        text,
        fontsize=8,
        color=MID,
        ha="left",
        va="bottom",
        fontfamily="sans-serif",
    )


def _set_title(fig: plt.Figure, title: str) -> None:
    """Set suptitle in large serif bold."""
    fig.suptitle(
        title,
        fontsize=16,
        fontweight="bold",
        color=DARK,
        x=0.5,
        y=0.98,
        ha="center",
        fontfamily="serif",
    )


# ---------------------------------------------------------------------------
# Individual chart renderers
# ---------------------------------------------------------------------------

def _render_bar(spec: ChartSpec, ax: plt.Axes, fig: plt.Figure) -> None:
    labels = spec.data["labels"]
    values = spec.data["values"]
    x = np.arange(len(labels))

    bars = ax.bar(x, values, color=AMBER, width=0.6, zorder=3)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=10)

    if spec.x_label:
        ax.set_xlabel(spec.x_label, fontsize=11)
    if spec.y_label:
        ax.set_ylabel(spec.y_label, fontsize=11)

    # Value labels on top of bars
    for bar, val in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + max(values) * 0.01,
            f"{val:g}",
            ha="center",
            va="bottom",
            fontsize=9,
            color=DARK,
        )

    _style_ax(ax)
    _set_title(fig, spec.title)
    source_text = spec.data.get("source") or spec.caption or ""
    if source_text:
        _add_source(fig, source_text)


def _render_line(spec: ChartSpec, ax: plt.Axes, fig: plt.Figure) -> None:
    series_list = spec.data["series"]

    for i, series in enumerate(series_list):
        color = _MULTI_PALETTE[i % len(_MULTI_PALETTE)]
        x_vals = series["x"]
        y_vals = series["y"]

        if all(isinstance(v, str) for v in x_vals):
            x_numeric = np.arange(len(x_vals))
            ax.plot(x_numeric, y_vals, color=color, linewidth=2, marker="o", markersize=5, label=series["label"], zorder=3)
            ax.set_xticks(x_numeric)
            ax.set_xticklabels(x_vals, rotation=30, ha="right", fontsize=10)
        else:
            ax.plot(x_vals, y_vals, color=color, linewidth=2, marker="o", markersize=5, label=series["label"], zorder=3)

    if len(series_list) > 1:
        ax.legend(loc="upper left")
    if spec.x_label:
        ax.set_xlabel(spec.x_label, fontsize=11)
    if spec.y_label:
        ax.set_ylabel(spec.y_label, fontsize=11)

    _style_ax(ax)
    _set_title(fig, spec.title)
    source_text = spec.data.get("source") or spec.caption or ""
    if source_text:
        _add_source(fig, source_text)


def _render_pie(spec: ChartSpec, ax: plt.Axes, fig: plt.Figure) -> None:
    labels = spec.data["labels"]
    values = spec.data["values"]
    center_text = spec.data.get("center_text")
    center_label = spec.data.get("center_label")

    # Build a palette: amber first, then stepped neutrals
    n = len(values)
    pie_colors = []
    neutrals = ["#B8862E", "#888888", "#AAAAAA", "#CCCCCC", "#999999", "#777777", "#BBBBBB"]
    for i in range(n):
        pie_colors.append(neutrals[i % len(neutrals)])

    wedges, texts, autotexts = ax.pie(
        values,
        labels=labels,
        colors=pie_colors,
        autopct="%1.0f%%",
        pctdistance=0.82,
        startangle=90,
        wedgeprops={"width": 0.55, "edgecolor": LIGHT, "linewidth": 2},
    )

    for txt in texts:
        txt.set_fontsize(10)
        txt.set_color(DARK)
    for atxt in autotexts:
        atxt.set_fontsize(9)
        atxt.set_color(WHITE)
        atxt.set_fontweight("bold")

    # Centred big number in the donut hole
    if center_text:
        ax.text(
            0, 0.1 if center_label else 0,
            center_text,
            ha="center",
            va="center",
            fontsize=22,
            fontweight="bold",
            color=DARK,
            fontfamily="serif",
        )
    if center_label:
        ax.text(
            0, -0.25,
            center_label,
            ha="center",
            va="center",
            fontsize=10,
            color=MID,
        )

    _set_title(fig, spec.title)
    source_text = spec.data.get("source") or spec.caption or ""
    if source_text:
        _add_source(fig, source_text)


def _render_stacked_bar(spec: ChartSpec, ax: plt.Axes, fig: plt.Figure) -> None:
    labels = spec.data["labels"]
    series_list = spec.data["series"]
    x = np.arange(len(labels))
    bottoms = np.zeros(len(labels))

    for i, series in enumerate(series_list):
        color = _MULTI_PALETTE[i % len(_MULTI_PALETTE)]
        vals = np.array(series["values"], dtype=float)
        ax.bar(x, vals, bottom=bottoms, color=color, width=0.6, label=series["label"], zorder=3)
        bottoms += vals

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=10)
    ax.legend(loc="upper right")

    if spec.x_label:
        ax.set_xlabel(spec.x_label, fontsize=11)
    if spec.y_label:
        ax.set_ylabel(spec.y_label, fontsize=11)

    _style_ax(ax)
    _set_title(fig, spec.title)
    source_text = spec.data.get("source") or spec.caption or ""
    if source_text:
        _add_source(fig, source_text)


def _render_waterfall(spec: ChartSpec, ax: plt.Axes, fig: plt.Figure) -> None:
    labels = spec.data["labels"]
    values = spec.data["values"]
    types = spec.data.get("types", ["positive"] * len(values))

    x = np.arange(len(labels))
    running = 0.0
    bar_bottoms = []
    bar_heights = []
    bar_colors = []

    for i, (val, typ) in enumerate(zip(values, types)):
        if typ == "base":
            bar_bottoms.append(0)
            bar_heights.append(val)
            bar_colors.append(_BASE_COLOR)
            running = val
        elif typ == "total":
            bar_bottoms.append(0)
            bar_heights.append(running + val if val == 0 else running)
            # If val is supplied as running total override
            bar_heights[-1] = running
            bar_colors.append(_TOTAL_COLOR)
        elif val >= 0:
            bar_bottoms.append(running)
            bar_heights.append(val)
            bar_colors.append(_POSITIVE_COLOR)
            running += val
        else:  # negative
            bar_bottoms.append(running + val)
            bar_heights.append(abs(val))
            bar_colors.append(_NEGATIVE_COLOR)
            running += val

    ax.bar(x, bar_heights, bottom=bar_bottoms, color=bar_colors, width=0.6, zorder=3)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=10)

    # Connector lines between bars
    for i in range(len(x) - 1):
        top_i = bar_bottoms[i] + bar_heights[i]
        ax.plot([x[i] + 0.3, x[i + 1] - 0.3], [top_i, top_i],
                color=MID, linewidth=0.8, linestyle="--", zorder=2)

    # Value labels
    for i, (bottom, height, val) in enumerate(zip(bar_bottoms, bar_heights, values)):
        label_y = bottom + height + max(bar_heights) * 0.02
        ax.text(x[i], label_y, f"{val:+g}" if val != 0 else f"{bottom + height:g}",
                ha="center", va="bottom", fontsize=9, color=DARK)

    # Legend patches
    legend_patches = [
        mpatches.Patch(color=_BASE_COLOR, label="База"),
        mpatches.Patch(color=_POSITIVE_COLOR, label="Рост"),
        mpatches.Patch(color=_NEGATIVE_COLOR, label="Снижение"),
        mpatches.Patch(color=_TOTAL_COLOR, label="Итог"),
    ]
    ax.legend(handles=legend_patches, loc="upper right", fontsize=9)

    if spec.x_label:
        ax.set_xlabel(spec.x_label, fontsize=11)
    if spec.y_label:
        ax.set_ylabel(spec.y_label, fontsize=11)

    _style_ax(ax)
    _set_title(fig, spec.title)
    source_text = spec.data.get("source") or spec.caption or ""
    if source_text:
        _add_source(fig, source_text)


def _render_scatter(spec: ChartSpec, ax: plt.Axes, fig: plt.Figure) -> None:
    series_list = spec.data["series"]

    for i, series in enumerate(series_list):
        color = _MULTI_PALETTE[i % len(_MULTI_PALETTE)]
        ax.scatter(
            series["x"],
            series["y"],
            color=color,
            label=series["label"],
            s=60,
            alpha=0.85,
            zorder=3,
            edgecolors=LIGHT,
            linewidths=0.5,
        )

    if len(series_list) > 1:
        ax.legend(loc="upper left")
    if spec.x_label:
        ax.set_xlabel(spec.x_label, fontsize=11)
    if spec.y_label:
        ax.set_ylabel(spec.y_label, fontsize=11)

    _style_ax(ax)
    _set_title(fig, spec.title)
    source_text = spec.data.get("source") or spec.caption or ""
    if source_text:
        _add_source(fig, source_text)


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

_RENDERERS = {
    "bar": _render_bar,
    "line": _render_line,
    "pie": _render_pie,
    "stacked_bar": _render_stacked_bar,
    "waterfall": _render_waterfall,
    "scatter": _render_scatter,
}

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def render_chart(spec: ChartSpec | object, output_path: Path) -> Path:
    """Render *spec* to a PNG file at *output_path*. Returns the resolved path.

    Args:
        spec: A ChartSpec dataclass instance **or** the pydantic ChartSpec from
              smart_report.models (duck-typed via .from_pydantic()).
        output_path: Destination file path. Parent directory must exist.

    Returns:
        The resolved absolute Path to the written PNG.

    Raises:
        ValueError: If chart_type is not one of the six supported types.
        KeyError: If spec.data is missing required keys for the given chart_type.
    """
    # Normalise to local dataclass if caller passed a pydantic model
    if not isinstance(spec, ChartSpec):
        spec = ChartSpec.from_pydantic(spec)

    chart_type = spec.chart_type
    renderer = _RENDERERS.get(chart_type)
    if renderer is None:
        raise ValueError(
            f"Unsupported chart_type {chart_type!r}. "
            f"Supported: {sorted(_RENDERERS)}"
        )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = _new_fig()
    try:
        renderer(spec, ax, fig)
        fig.tight_layout(rect=[0, 0.06, 1, 0.94])
        fig.savefig(output_path, format="png", bbox_inches="tight")
    finally:
        plt.close(fig)

    return output_path.resolve()
