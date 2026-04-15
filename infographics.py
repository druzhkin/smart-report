"""Generate infographics (PNG) from a Report: matrix map, connections graph,
metrics dashboard, priority heatmap. Reused by DOCX and PPTX exports.

All outputs go to reports/images/ with deterministic filenames based on a slug.
"""
from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Iterable

import matplotlib
matplotlib.use("Agg")
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

from models import Block, BlockHeader, Connection, Report

# ---------- palette (McKinsey-esque navy + accents) ----------

NAVY = "#1B3A5C"
NAVY_LIGHT = "#2E5984"
GREY_BG = "#F5F5F5"
GREY_MID = "#BDBDBD"
RED = "#C0392B"
YELLOW = "#F1C40F"
GREEN = "#27AE60"
BLUE = "#2E86C1"
WHITE = "#FFFFFF"

PRIORITY_COLOR = {"high": RED, "medium": YELLOW, "low": GREEN}
PRIORITY_FALLBACK = GREY_MID

NATURE_COLOR = {
    "paradox": RED,
    "causal_chain": BLUE,
    "unexpected_confirmation": GREEN,
    "shared_variable": NAVY_LIGHT,
}

STRENGTH_WIDTH = {"strong": 3.2, "moderate": 2.0, "speculative": 1.0}

IMAGES_DIR = Path(__file__).parent / "reports" / "images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)


# ---------- helpers ----------

def _slugify(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE).strip().lower()
    text = re.sub(r"[\s_]+", "-", text)
    return text[:50] or "report"


def _headers_by_cell(report: Report) -> dict[str, BlockHeader]:
    return {h.cell: h for h in report.block_headers}


def _domain_priority(report: Report, domain: str) -> str:
    """Worst-case priority across cells of domain (high > medium > low)."""
    headers = _headers_by_cell(report)
    score = {"high": 3, "medium": 2, "low": 1}
    best = 0
    for h in headers.values():
        dom = h.cell.split(" / ", 1)[0].strip()
        if dom == domain:
            best = max(best, score.get(h.priority, 0))
    return {3: "high", 2: "medium", 1: "low"}.get(best, "low")


def _cell_priority(report: Report, cell: str) -> str:
    headers = _headers_by_cell(report)
    h = headers.get(cell)
    return h.priority if h else "low"


def _extract_numbers_from_blocks(report: Report, limit: int = 8) -> list[tuple[str, str, str]]:
    """Return list of (number, context, source). Prefers strongest_number from headers."""
    out: list[tuple[str, str, str]] = []
    headers = _headers_by_cell(report)
    # Prefer strongest_number from headers (sorted by priority)
    prio_order = {"high": 0, "medium": 1, "low": 2}
    sorted_headers = sorted(
        headers.values(), key=lambda h: prio_order.get(h.priority, 3)
    )
    num_re = re.compile(r"[-+]?\d[\d.,]*\s*%?")
    for h in sorted_headers:
        if not h.strongest_number:
            continue
        m = num_re.search(h.strongest_number)
        if not m:
            continue
        num = m.group(0).strip()
        context = h.strongest_number.replace(num, "").strip(" —-:,") or h.one_liner
        out.append((num, context[:70], h.cell))
        if len(out) >= limit:
            return out

    # Fallback: scan block findings
    if len(out) < limit:
        for b in report.blocks:
            for f in b.findings:
                if not f.has_numbers:
                    continue
                m = num_re.search(f.claim)
                if not m:
                    continue
                num = m.group(0).strip()
                context = f.claim[:70]
                out.append((num, context, b.cell))
                if len(out) >= limit:
                    return out
    return out


def _wrap(text: str, width: int) -> str:
    words = text.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        candidate = (cur + " " + w).strip() if cur else w
        if len(candidate) <= width:
            cur = candidate
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return "\n".join(lines)


# ---------- 1. matrix map ----------

def render_matrix_map(report: Report, out_path: Path | None = None) -> Path:
    """Domains as coloured blocks (priority colour), layers listed inside."""
    domains = report.matrix.domains
    n = len(domains)
    if n == 0:
        # empty placeholder
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.text(0.5, 0.5, "Матрица пуста", ha="center", va="center", fontsize=14)
        ax.axis("off")
        path = out_path or IMAGES_DIR / f"{_slugify(report.goal)}-matrix.png"
        fig.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        return path

    cols = min(3, n)
    rows = math.ceil(n / cols)
    fig, ax = plt.subplots(figsize=(cols * 4.2, rows * 3.6))
    ax.set_xlim(0, cols)
    ax.set_ylim(0, rows)
    ax.invert_yaxis()
    ax.axis("off")
    ax.set_title("Карта матрицы доменов", fontsize=16, color=NAVY, weight="bold", pad=14)

    for idx, d in enumerate(domains):
        r, c = divmod(idx, cols)
        x = c + 0.05
        y = r + 0.05
        w = 0.9
        h = 0.9
        prio = _domain_priority(report, d.name)
        color = PRIORITY_COLOR.get(prio, PRIORITY_FALLBACK)
        box = FancyBboxPatch(
            (x, y), w, h,
            boxstyle="round,pad=0.02,rounding_size=0.04",
            linewidth=1.5, edgecolor=NAVY, facecolor=color, alpha=0.85,
        )
        ax.add_patch(box)
        ax.text(
            x + w / 2, y + 0.12, _wrap(d.name, 28),
            ha="center", va="top", fontsize=11, color=WHITE, weight="bold",
        )
        layer_txt = "\n".join(f"• {_wrap(l.name, 26)}" for l in d.layers[:5])
        ax.text(
            x + 0.05, y + 0.32, layer_txt,
            ha="left", va="top", fontsize=8.5, color=WHITE,
        )

    # legend
    legend_patches = [
        mpatches.Patch(color=RED, label="Высокий приоритет"),
        mpatches.Patch(color=YELLOW, label="Средний приоритет"),
        mpatches.Patch(color=GREEN, label="Низкий приоритет"),
    ]
    ax.legend(
        handles=legend_patches, loc="lower center",
        bbox_to_anchor=(0.5, -0.03), ncol=3, frameon=False, fontsize=9,
    )

    path = out_path or IMAGES_DIR / f"{_slugify(report.goal)}-matrix.png"
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=WHITE)
    plt.close(fig)
    return path


# ---------- 2. connections graph ----------

def render_connections_graph(report: Report, out_path: Path | None = None) -> Path:
    """Nodes = domains; edges = connections. Width=strength, colour=nature."""
    domains = [d.name for d in report.matrix.domains]
    n = len(domains)

    fig, ax = plt.subplots(figsize=(10, 8))
    ax.set_title("Граф кросс-доменных связей", fontsize=16, color=NAVY, weight="bold", pad=14)
    ax.set_aspect("equal")
    ax.axis("off")

    if n == 0:
        ax.text(0.5, 0.5, "Нет доменов", ha="center", va="center", fontsize=14,
                transform=ax.transAxes)
        path = out_path or IMAGES_DIR / f"{_slugify(report.goal)}-graph.png"
        fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=WHITE)
        plt.close(fig)
        return path

    # positions: circle layout
    radius = 1.0
    pos: dict[str, tuple[float, float]] = {}
    for i, dom in enumerate(domains):
        angle = 2 * math.pi * i / max(n, 1) - math.pi / 2
        pos[dom] = (radius * math.cos(angle), radius * math.sin(angle))

    # draw edges
    for conn in report.connections:
        doms = [d for d in conn.domains if d in pos]
        if len(doms) < 2:
            continue
        color = NATURE_COLOR.get(conn.nature, NAVY_LIGHT)
        lw = STRENGTH_WIDTH.get(conn.strength, 1.5)
        for i in range(len(doms)):
            for j in range(i + 1, len(doms)):
                x1, y1 = pos[doms[i]]
                x2, y2 = pos[doms[j]]
                ax.plot([x1, x2], [y1, y2], color=color, linewidth=lw, alpha=0.6, zorder=1)

    # draw nodes
    for dom, (x, y) in pos.items():
        prio = _domain_priority(report, dom)
        color = PRIORITY_COLOR.get(prio, PRIORITY_FALLBACK)
        ax.scatter([x], [y], s=2200, color=color, edgecolors=NAVY, linewidths=2, zorder=2)
        ax.text(x, y, _wrap(dom, 16), ha="center", va="center",
                fontsize=9, color=WHITE, weight="bold", zorder=3)

    ax.set_xlim(-1.6, 1.6)
    ax.set_ylim(-1.6, 1.6)

    # legend
    legend_handles = [
        mpatches.Patch(color=RED, label="Парадокс"),
        mpatches.Patch(color=BLUE, label="Причинная цепочка"),
        mpatches.Patch(color=GREEN, label="Подтверждение"),
        mpatches.Patch(color=NAVY_LIGHT, label="Общая переменная"),
    ]
    ax.legend(handles=legend_handles, loc="lower center",
              bbox_to_anchor=(0.5, -0.05), ncol=4, frameon=False, fontsize=9)

    # subtitle
    ax.text(0, 1.45,
            f"Узел = домен · цвет = приоритет · толщина линии = сила связи ({len(report.connections)} связей)",
            ha="center", fontsize=9, color=NAVY, style="italic")

    path = out_path or IMAGES_DIR / f"{_slugify(report.goal)}-graph.png"
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=WHITE)
    plt.close(fig)
    return path


# ---------- 3. metrics dashboard ----------

def render_metrics_dashboard(report: Report, out_path: Path | None = None) -> Path:
    """6-8 key numbers laid out as large-font tiles, McKinsey style."""
    metrics = _extract_numbers_from_blocks(report, limit=8)

    fig, ax = plt.subplots(figsize=(12, 7))
    ax.set_xlim(0, 4)
    ax.set_ylim(0, 2)
    ax.invert_yaxis()
    ax.axis("off")
    ax.set_title("Key Metrics Dashboard", fontsize=18, color=NAVY, weight="bold", pad=14)

    if not metrics:
        ax.text(2, 1, "Недостаточно количественных данных в отчёте",
                ha="center", va="center", fontsize=14, color=GREY_MID)
        path = out_path or IMAGES_DIR / f"{_slugify(report.goal)}-metrics.png"
        fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=WHITE)
        plt.close(fig)
        return path

    # grid 4x2
    cols = 4
    for idx, (num, context, source) in enumerate(metrics[:8]):
        r, c = divmod(idx, cols)
        x = c + 0.03
        y = r + 0.03
        w = 0.94
        h = 0.94
        box = FancyBboxPatch(
            (x, y), w, h,
            boxstyle="round,pad=0.02,rounding_size=0.03",
            linewidth=1.0, edgecolor=NAVY, facecolor=GREY_BG,
        )
        ax.add_patch(box)
        # big number
        ax.text(x + w / 2, y + 0.35, num,
                ha="center", va="center", fontsize=28, color=NAVY, weight="bold")
        # context
        ax.text(x + w / 2, y + 0.62, _wrap(context, 32),
                ha="center", va="center", fontsize=9, color="#333333")
        # source
        ax.text(x + w / 2, y + 0.88, f"[{_wrap(source, 36)}]",
                ha="center", va="center", fontsize=7.5, color=GREY_MID, style="italic")

    path = out_path or IMAGES_DIR / f"{_slugify(report.goal)}-metrics.png"
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=WHITE)
    plt.close(fig)
    return path


# ---------- 4. priority heatmap ----------

def render_priority_heatmap(report: Report, out_path: Path | None = None) -> Path:
    """Matrix: domains (rows) × layers (cols), cell colour = priority."""
    domains = report.matrix.domains
    if not domains:
        fig, ax = plt.subplots(figsize=(8, 3))
        ax.text(0.5, 0.5, "Матрица пуста", ha="center", va="center", fontsize=14)
        ax.axis("off")
        path = out_path or IMAGES_DIR / f"{_slugify(report.goal)}-heatmap.png"
        fig.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        return path

    max_layers = max((len(d.layers) for d in domains), default=1)
    n_domains = len(domains)

    score = {"high": 3, "medium": 2, "low": 1}
    color_map = {3: RED, 2: YELLOW, 1: GREEN, 0: GREY_BG}

    fig_w = max(8, 1.6 * max_layers + 4)
    fig_h = max(3, 0.7 * n_domains + 2)
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    ax.set_xlim(0, max_layers)
    ax.set_ylim(0, n_domains)
    ax.invert_yaxis()
    ax.set_title("Тепловая карта приоритетов: где золото, где пусто",
                 fontsize=15, color=NAVY, weight="bold", pad=14)

    for r, d in enumerate(domains):
        for c, layer in enumerate(d.layers[:max_layers]):
            cell_key = f"{d.name} / {layer.name}"
            prio = _cell_priority(report, cell_key)
            val = score.get(prio, 0)
            color = color_map.get(val, GREY_BG)
            rect = plt.Rectangle((c, r), 1, 1, facecolor=color, edgecolor=NAVY, linewidth=0.8)
            ax.add_patch(rect)
            label = _wrap(layer.name, 14)
            ax.text(c + 0.5, r + 0.5, label, ha="center", va="center",
                    fontsize=8, color=WHITE if val >= 2 else "#222222", weight="bold")

    # row labels (domain names) on the left outside the grid
    ax.set_yticks([r + 0.5 for r in range(n_domains)])
    ax.set_yticklabels([_wrap(d.name, 22) for d in domains], fontsize=9, color=NAVY)
    ax.set_xticks([c + 0.5 for c in range(max_layers)])
    ax.set_xticklabels([f"Слой {c+1}" for c in range(max_layers)], fontsize=9, color=NAVY)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(left=False, bottom=False)

    legend_patches = [
        mpatches.Patch(color=RED, label="Высокий"),
        mpatches.Patch(color=YELLOW, label="Средний"),
        mpatches.Patch(color=GREEN, label="Низкий"),
        mpatches.Patch(color=GREY_BG, label="Нет данных"),
    ]
    ax.legend(handles=legend_patches, loc="lower center",
              bbox_to_anchor=(0.5, -0.2), ncol=4, frameon=False, fontsize=9)

    path = out_path or IMAGES_DIR / f"{_slugify(report.goal)}-heatmap.png"
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=WHITE)
    plt.close(fig)
    return path


# ---------- convenience ----------

def render_all(report: Report, stem: str | None = None) -> dict[str, Path]:
    base = stem or _slugify(report.goal)
    paths = {
        "matrix": IMAGES_DIR / f"{base}-matrix.png",
        "graph": IMAGES_DIR / f"{base}-graph.png",
        "metrics": IMAGES_DIR / f"{base}-metrics.png",
        "heatmap": IMAGES_DIR / f"{base}-heatmap.png",
    }
    render_matrix_map(report, paths["matrix"])
    render_connections_graph(report, paths["graph"])
    render_metrics_dashboard(report, paths["metrics"])
    render_priority_heatmap(report, paths["heatmap"])
    return paths
