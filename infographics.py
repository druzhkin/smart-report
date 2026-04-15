"""Generate infographics (PNG) from a Report: matrix map, connections graph,
metrics dashboard, priority heatmap. Reused by DOCX and PPTX exports.

Titles are intentionally NOT rendered into the image — the host document
(Word/PPTX) adds its own heading, so the image stays clean.
"""
from __future__ import annotations

import math
import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

from models import BlockHeader, Report

# ---------- palette ----------

NAVY = "#1B3A5C"
NAVY_LIGHT = "#2E5984"
INK = "#1F2937"
SOFT_BG = "#F8FAFC"
CARD_BG = "#FFFFFF"
BORDER = "#E2E8F0"
MUTED = "#64748B"
RED = "#DC2626"
AMBER = "#F59E0B"
GREEN = "#16A34A"
BLUE = "#2563EB"
VIOLET = "#7C3AED"
WHITE = "#FFFFFF"

PRIORITY_COLOR = {"high": RED, "medium": AMBER, "low": GREEN}
PRIORITY_FALLBACK = "#CBD5E1"

NATURE_COLOR = {
    "paradox": RED,
    "causal_chain": BLUE,
    "unexpected_confirmation": GREEN,
    "shared_variable": VIOLET,
}

STRENGTH_WIDTH = {"strong": 3.4, "moderate": 2.2, "speculative": 1.2}

IMAGES_DIR = Path(__file__).parent / "reports" / "images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "axes.edgecolor": BORDER,
    "axes.linewidth": 0.6,
})


# ---------- helpers ----------

def _slugify(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE).strip().lower()
    text = re.sub(r"[\s_]+", "-", text)
    return text[:50] or "report"


def _headers_by_cell(report: Report) -> dict[str, BlockHeader]:
    return {h.cell: h for h in report.block_headers}


def _domain_priority(report: Report, domain: str) -> str:
    headers = _headers_by_cell(report)
    score = {"high": 3, "medium": 2, "low": 1}
    best = 0
    for h in headers.values():
        dom = h.cell.split(" / ", 1)[0].strip()
        if dom == domain:
            best = max(best, score.get(h.priority, 0))
    return {3: "high", 2: "medium", 1: "low"}.get(best, "low")


def _cell_priority(report: Report, cell: str) -> str:
    h = _headers_by_cell(report).get(cell)
    return h.priority if h else "low"


def _wrap(text: str, width: int) -> str:
    words = text.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        cand = (cur + " " + w).strip() if cur else w
        if len(cand) <= width:
            cur = cand
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return "\n".join(lines)


def _extract_numbers_from_blocks(report: Report, limit: int = 6) -> list[tuple[str, str, str]]:
    out: list[tuple[str, str, str]] = []
    headers = _headers_by_cell(report)
    prio_order = {"high": 0, "medium": 1, "low": 2}
    sorted_headers = sorted(headers.values(), key=lambda h: prio_order.get(h.priority, 3))
    num_re = re.compile(r"[-+]?\d[\d.,]*\s*%?")
    seen: set[str] = set()
    for h in sorted_headers:
        if not h.strongest_number:
            continue
        m = num_re.search(h.strongest_number)
        if not m:
            continue
        num = m.group(0).strip()
        if num in seen:
            continue
        seen.add(num)
        context = h.strongest_number.replace(num, "").strip(" —-:,·")
        if not context:
            context = h.one_liner or ""
        out.append((num, context[:80], h.cell))
        if len(out) >= limit:
            return out
    if len(out) < limit:
        for b in report.blocks:
            for f in b.findings:
                if not f.has_numbers:
                    continue
                m = num_re.search(f.claim)
                if not m:
                    continue
                num = m.group(0).strip()
                if num in seen:
                    continue
                seen.add(num)
                out.append((num, f.claim[:80], b.cell))
                if len(out) >= limit:
                    return out
    return out


# ---------- 1. matrix map ----------

def render_matrix_map(report: Report, out_path: Path | None = None) -> Path:
    """Domain cards: navy title strip on top, white body with layer bullets."""
    domains = report.matrix.domains
    n = len(domains)
    path = out_path or IMAGES_DIR / f"{_slugify(report.goal)}-matrix.png"

    if n == 0:
        fig, ax = plt.subplots(figsize=(8, 3))
        ax.text(0.5, 0.5, "Матрица пуста", ha="center", va="center", fontsize=14, color=MUTED)
        ax.axis("off")
        fig.savefig(path, dpi=180, bbox_inches="tight", facecolor=WHITE)
        plt.close(fig)
        return path

    cols = min(3, n)
    rows = math.ceil(n / cols)
    fig, ax = plt.subplots(figsize=(cols * 4.6, rows * 4.2))
    ax.set_xlim(0, cols)
    ax.set_ylim(0, rows)
    ax.invert_yaxis()
    ax.axis("off")
    fig.patch.set_facecolor(WHITE)

    for idx, d in enumerate(domains):
        r, c = divmod(idx, cols)
        x, y, w, h = c + 0.08, r + 0.06, 0.84, 0.88
        prio = _domain_priority(report, d.name)
        accent = PRIORITY_COLOR.get(prio, PRIORITY_FALLBACK)

        # card body
        body = FancyBboxPatch(
            (x, y), w, h,
            boxstyle="round,pad=0.01,rounding_size=0.035",
            linewidth=0.8, edgecolor=BORDER, facecolor=CARD_BG, zorder=1,
        )
        ax.add_patch(body)

        # navy title strip
        strip_h = 0.22
        strip = FancyBboxPatch(
            (x, y), w, strip_h,
            boxstyle="round,pad=0.01,rounding_size=0.035",
            linewidth=0, facecolor=NAVY, zorder=2,
        )
        ax.add_patch(strip)
        # mask bottom rounding of strip
        ax.add_patch(plt.Rectangle(
            (x, y + strip_h - 0.04), w, 0.04,
            facecolor=NAVY, linewidth=0, zorder=2,
        ))

        # priority dot
        ax.add_patch(plt.Circle(
            (x + w - 0.07, y + strip_h / 2), 0.028,
            facecolor=accent, edgecolor=WHITE, linewidth=1.2, zorder=4,
        ))

        # domain title
        ax.text(
            x + 0.04, y + strip_h / 2, _wrap(d.name, 26),
            ha="left", va="center", fontsize=11.5, color=WHITE, weight="bold", zorder=3,
        )

        # layers
        layer_lines = [f"•  {_wrap(l.name, 32)}" for l in d.layers[:6]]
        ax.text(
            x + 0.05, y + strip_h + 0.06, "\n".join(layer_lines),
            ha="left", va="top", fontsize=9.2, color=INK, zorder=3, linespacing=1.5,
        )

    legend = [
        mpatches.Patch(color=RED, label="Высокий приоритет"),
        mpatches.Patch(color=AMBER, label="Средний"),
        mpatches.Patch(color=GREEN, label="Низкий"),
    ]
    ax.legend(
        handles=legend, loc="lower center",
        bbox_to_anchor=(0.5, -0.04), ncol=3, frameon=False, fontsize=10,
    )

    fig.savefig(path, dpi=180, bbox_inches="tight", facecolor=WHITE)
    plt.close(fig)
    return path


# ---------- 2. connections graph ----------

def render_connections_graph(report: Report, out_path: Path | None = None) -> Path:
    """Nodes = all domains that appear anywhere (matrix OR connections).
    Edges curved slightly to disambiguate multi-links between same pair.
    """
    path = out_path or IMAGES_DIR / f"{_slugify(report.goal)}-graph.png"

    # collect ALL domains referenced
    domain_set: list[str] = []
    seen: set[str] = set()
    for d in report.matrix.domains:
        if d.name not in seen:
            seen.add(d.name)
            domain_set.append(d.name)
    for c in report.connections:
        for dom in c.domains:
            if dom and dom not in seen:
                seen.add(dom)
                domain_set.append(dom)

    n = len(domain_set)
    fig, ax = plt.subplots(figsize=(11, 8.5))
    fig.patch.set_facecolor(WHITE)
    ax.set_aspect("equal")
    ax.axis("off")

    if n == 0:
        ax.text(0.5, 0.5, "Нет доменов", ha="center", va="center", fontsize=14,
                color=MUTED, transform=ax.transAxes)
        fig.savefig(path, dpi=180, bbox_inches="tight", facecolor=WHITE)
        plt.close(fig)
        return path

    # positions: circle
    radius = 1.0 if n > 1 else 0.0
    pos: dict[str, tuple[float, float]] = {}
    for i, dom in enumerate(domain_set):
        angle = 2 * math.pi * i / max(n, 1) - math.pi / 2
        pos[dom] = (radius * math.cos(angle), radius * math.sin(angle))

    # count edges per pair for curvature offset
    pair_count: dict[tuple[str, str], int] = {}

    # edges
    for conn in report.connections:
        doms = [d for d in conn.domains if d in pos]
        if len(doms) < 2:
            continue
        color = NATURE_COLOR.get(conn.nature, NAVY_LIGHT)
        lw = STRENGTH_WIDTH.get(conn.strength, 1.8)
        for i in range(len(doms)):
            for j in range(i + 1, len(doms)):
                key = tuple(sorted([doms[i], doms[j]]))
                k = pair_count.get(key, 0)
                pair_count[key] = k + 1
                x1, y1 = pos[doms[i]]
                x2, y2 = pos[doms[j]]
                rad = 0.08 * ((k % 4) - 1.5)
                ax.annotate(
                    "", xy=(x2, y2), xytext=(x1, y1),
                    arrowprops=dict(
                        arrowstyle="-", color=color, linewidth=lw, alpha=0.65,
                        connectionstyle=f"arc3,rad={rad}",
                    ),
                    zorder=1,
                )

    # nodes
    node_r = 0.18 if n <= 6 else 0.14
    for dom, (x, y) in pos.items():
        prio = _domain_priority(report, dom)
        color = PRIORITY_COLOR.get(prio, PRIORITY_FALLBACK)
        circ = plt.Circle(
            (x, y), node_r,
            facecolor=color, edgecolor=WHITE, linewidth=2.5, zorder=3,
        )
        ax.add_patch(circ)
        # shadow
        ax.add_patch(plt.Circle(
            (x, y - 0.008), node_r,
            facecolor="#00000020", edgecolor="none", zorder=2,
        ))
        ax.text(
            x, y - node_r - 0.12, _wrap(dom, 20),
            ha="center", va="top", fontsize=9.5, color=INK, weight="bold", zorder=4,
        )

    margin = node_r + 0.55
    ax.set_xlim(-1 - margin, 1 + margin)
    ax.set_ylim(-1 - margin, 1 + margin)

    legend = [
        mpatches.Patch(color=RED, label="Парадокс"),
        mpatches.Patch(color=BLUE, label="Причинная цепочка"),
        mpatches.Patch(color=GREEN, label="Подтверждение"),
        mpatches.Patch(color=VIOLET, label="Общая переменная"),
    ]
    ax.legend(
        handles=legend, loc="lower center",
        bbox_to_anchor=(0.5, -0.02), ncol=4, frameon=False, fontsize=10,
    )
    ax.text(
        0, 1 + margin - 0.12,
        f"{n} доменов · {len(report.connections)} связей · толщина = сила",
        ha="center", fontsize=9.5, color=MUTED, style="italic",
    )

    fig.savefig(path, dpi=180, bbox_inches="tight", facecolor=WHITE)
    plt.close(fig)
    return path


# ---------- 3. metrics dashboard ----------

def render_metrics_dashboard(report: Report, out_path: Path | None = None) -> Path:
    """Max 6 metric tiles, large number, subtle shadow, clear hierarchy."""
    path = out_path or IMAGES_DIR / f"{_slugify(report.goal)}-metrics.png"
    metrics = _extract_numbers_from_blocks(report, limit=6)

    if not metrics:
        fig, ax = plt.subplots(figsize=(10, 3))
        ax.text(0.5, 0.5, "Недостаточно количественных данных",
                ha="center", va="center", fontsize=13, color=MUTED)
        ax.axis("off")
        fig.savefig(path, dpi=180, bbox_inches="tight", facecolor=WHITE)
        plt.close(fig)
        return path

    k = len(metrics)
    cols = 3 if k >= 3 else k
    rows = math.ceil(k / cols)

    fig, ax = plt.subplots(figsize=(cols * 4.2, rows * 3.4))
    ax.set_xlim(0, cols)
    ax.set_ylim(0, rows)
    ax.invert_yaxis()
    ax.axis("off")
    fig.patch.set_facecolor(WHITE)

    accents = [BLUE, NAVY, VIOLET, GREEN, AMBER, RED]

    for idx, (num, context, source) in enumerate(metrics):
        r, c = divmod(idx, cols)
        x, y, w, h = c + 0.06, r + 0.06, 0.88, 0.88
        accent = accents[idx % len(accents)]

        # soft shadow
        ax.add_patch(FancyBboxPatch(
            (x + 0.015, y + 0.025), w, h,
            boxstyle="round,pad=0.01,rounding_size=0.035",
            linewidth=0, facecolor="#0F172A10", zorder=1,
        ))
        # card
        ax.add_patch(FancyBboxPatch(
            (x, y), w, h,
            boxstyle="round,pad=0.01,rounding_size=0.035",
            linewidth=0.8, edgecolor=BORDER, facecolor=CARD_BG, zorder=2,
        ))
        # accent top bar
        ax.add_patch(plt.Rectangle(
            (x + 0.02, y + 0.04), w - 0.04, 0.03,
            facecolor=accent, linewidth=0, zorder=3,
        ))

        # big number
        ax.text(
            x + w / 2, y + 0.32, num,
            ha="center", va="center", fontsize=34, color=NAVY, weight="bold", zorder=4,
        )
        # context
        ax.text(
            x + w / 2, y + 0.62, _wrap(context, 34),
            ha="center", va="center", fontsize=10, color=INK, zorder=4, linespacing=1.4,
        )
        # source
        ax.text(
            x + w / 2, y + h - 0.06, _wrap(source, 40),
            ha="center", va="center", fontsize=8, color=MUTED, style="italic", zorder=4,
        )

    fig.savefig(path, dpi=180, bbox_inches="tight", facecolor=WHITE)
    plt.close(fig)
    return path


# ---------- 4. priority heatmap ----------

def render_priority_heatmap(report: Report, out_path: Path | None = None) -> Path:
    """Domains × layers; cells coloured by priority with readable labels."""
    path = out_path or IMAGES_DIR / f"{_slugify(report.goal)}-heatmap.png"
    domains = report.matrix.domains

    if not domains:
        fig, ax = plt.subplots(figsize=(8, 3))
        ax.text(0.5, 0.5, "Матрица пуста", ha="center", va="center", fontsize=14, color=MUTED)
        ax.axis("off")
        fig.savefig(path, dpi=180, bbox_inches="tight", facecolor=WHITE)
        plt.close(fig)
        return path

    max_layers = max((len(d.layers) for d in domains), default=1)
    n_domains = len(domains)

    score = {"high": 3, "medium": 2, "low": 1}
    color_map = {3: RED, 2: AMBER, 1: GREEN, 0: "#F1F5F9"}

    fig_w = max(10, 2.3 * max_layers + 3.5)
    fig_h = max(4, 1.1 * n_domains + 1.8)
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    fig.patch.set_facecolor(WHITE)
    ax.set_xlim(0, max_layers)
    ax.set_ylim(0, n_domains)
    ax.invert_yaxis()

    for r, d in enumerate(domains):
        for c in range(max_layers):
            layer = d.layers[c] if c < len(d.layers) else None
            if layer is None:
                color = color_map[0]
                label = ""
                val = 0
            else:
                prio = _cell_priority(report, f"{d.name} / {layer.name}")
                val = score.get(prio, 0)
                color = color_map.get(val, color_map[0])
                label = _wrap(layer.name, 16)
            # cell with subtle inset
            ax.add_patch(plt.Rectangle(
                (c + 0.04, r + 0.04), 0.92, 0.92,
                facecolor=color, edgecolor="none",
            ))
            if label:
                ax.text(
                    c + 0.5, r + 0.5, label,
                    ha="center", va="center",
                    fontsize=9.5 if len(label) < 30 else 8.5,
                    color=WHITE if val >= 2 else INK, weight="bold",
                )

    ax.set_yticks([r + 0.5 for r in range(n_domains)])
    ax.set_yticklabels([_wrap(d.name, 24) for d in domains], fontsize=10, color=INK)
    ax.set_xticks([c + 0.5 for c in range(max_layers)])
    ax.set_xticklabels([f"Слой {c+1}" for c in range(max_layers)], fontsize=10, color=MUTED)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(left=False, bottom=False)

    legend = [
        mpatches.Patch(color=RED, label="Высокий"),
        mpatches.Patch(color=AMBER, label="Средний"),
        mpatches.Patch(color=GREEN, label="Низкий"),
        mpatches.Patch(color=color_map[0], label="Нет данных"),
    ]
    ax.legend(
        handles=legend, loc="lower center",
        bbox_to_anchor=(0.5, -0.16), ncol=4, frameon=False, fontsize=10,
    )

    fig.savefig(path, dpi=180, bbox_inches="tight", facecolor=WHITE)
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
