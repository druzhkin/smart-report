/**
 * part2_sections.js — Document section builders for the consulting report.
 *
 * Exports:
 *   buildCoverPage(data)           → Paragraph[] (cover, own Section, no headers/footers)
 *   buildExecutiveSummary(data)    → Array<Paragraph|Table>
 *   buildTableOfContents(tocItems) → Array<Paragraph|Table>
 *   buildMainChapters(data)        → Array<Paragraph|Table>
 *   buildSourcesSection(sources)   → Array<Paragraph|Table>
 *
 * data = the parsed FinalReport JSON object.
 */

import {
  AlignmentType,
  BorderStyle,
  HeightRule,
  ImageRun,
  Paragraph,
  ShadingType,
  Table,
  TableBorders,
  TableCell,
  TableRow,
  TextRun,
  WidthType,
} from "docx";
import fs from "fs";
import path from "path";

import {
  C,
  CONTENT_WIDTH_DXA,
  H1,
  H2,
  H3,
  P,
  R,
  bullet,
  callout,
  caption,
  dataTable,
  embedImage,
  kpiRow,
  numbered,
  pageBreak,
  parseMarkdownBlocks,
  parseInlineMarkdown,
  spacer,
  hr,
} from "./part1_core.js";

const FONT = "Calibri";

// ---------------------------------------------------------------------------
// Cover page (Section 1 — no headers/footers)
// ---------------------------------------------------------------------------

/**
 * buildCoverPage(data) — builds the cover page paragraphs.
 * Includes: navy banner, title, subtitle, date, author, page break.
 * @param {{ question: string, session_id: string, metadata?: object }} data
 * @returns {Array<Table|Paragraph>}
 */
export function buildCoverPage(data) {
  const elements = [];

  const title = truncateTitle(data.question ?? "Аналитический отчёт", 120);
  const subtitle = "Аналитический отчёт";
  const dateStr = formatDateRu(new Date());
  const authorStr = "Smart Report AI";

  // Top spacer
  elements.push(spacer(400));

  // Banner — navy full-width table
  const bannerRow = new TableRow({
    height: { value: 1200, rule: HeightRule.EXACT },
    children: [
      new TableCell({
        width: { size: CONTENT_WIDTH_DXA, type: WidthType.DXA },
        shading: {
          type: ShadingType.CLEAR,
          fill: C.primary,
          color: "auto",
        },
        borders: {
          top: { style: BorderStyle.NONE, size: 0, color: "auto" },
          bottom: { style: BorderStyle.NONE, size: 0, color: "auto" },
          left: { style: BorderStyle.NONE, size: 0, color: "auto" },
          right: { style: BorderStyle.NONE, size: 0, color: "auto" },
        },
        margins: { top: 200, bottom: 200, left: 400, right: 400 },
        children: [
          new Paragraph({
            children: [
              new TextRun({
                text: subtitle,
                font: FONT,
                bold: true,
                color: C.accent,
                size: 32,  // 16pt
              }),
            ],
            alignment: AlignmentType.LEFT,
            spacing: { before: 0, after: 60 },
          }),
        ],
      }),
    ],
  });

  elements.push(new Table({
    width: { size: CONTENT_WIDTH_DXA, type: WidthType.DXA },
    columnWidths: [CONTENT_WIDTH_DXA],
    borders: TableBorders.NONE,
    rows: [bannerRow],
  }));

  elements.push(spacer(300));

  // Title — large, primary color
  elements.push(new Paragraph({
    children: [
      new TextRun({
        text: title,
        font: FONT,
        bold: true,
        color: C.primary,
        size: 72,  // 36pt
      }),
    ],
    spacing: { before: 0, after: 240 },
  }));

  // Gold separator line
  elements.push(hr(C.accent, 12));
  elements.push(spacer(200));

  // Date and author meta block
  const metaRow = new TableRow({
    children: [
      new TableCell({
        width: { size: Math.floor(CONTENT_WIDTH_DXA / 2), type: WidthType.DXA },
        borders: {
          top: { style: BorderStyle.NONE, size: 0, color: "auto" },
          bottom: { style: BorderStyle.NONE, size: 0, color: "auto" },
          left: { style: BorderStyle.NONE, size: 0, color: "auto" },
          right: { style: BorderStyle.NONE, size: 0, color: "auto" },
        },
        children: [
          new Paragraph({
            children: [
              new TextRun({ text: "Дата", font: FONT, color: C.textMuted, size: 18 }),
            ],
          }),
          new Paragraph({
            children: [
              new TextRun({ text: dateStr, font: FONT, bold: true, color: C.textDark, size: 24 }),
            ],
          }),
        ],
      }),
      new TableCell({
        width: { size: Math.floor(CONTENT_WIDTH_DXA / 2), type: WidthType.DXA },
        borders: {
          top: { style: BorderStyle.NONE, size: 0, color: "auto" },
          bottom: { style: BorderStyle.NONE, size: 0, color: "auto" },
          left: { style: BorderStyle.NONE, size: 0, color: "auto" },
          right: { style: BorderStyle.NONE, size: 0, color: "auto" },
        },
        children: [
          new Paragraph({
            children: [
              new TextRun({ text: "Подготовлено", font: FONT, color: C.textMuted, size: 18 }),
            ],
          }),
          new Paragraph({
            children: [
              new TextRun({ text: authorStr, font: FONT, bold: true, color: C.textDark, size: 24 }),
            ],
          }),
        ],
      }),
    ],
  });

  elements.push(new Table({
    width: { size: CONTENT_WIDTH_DXA, type: WidthType.DXA },
    columnWidths: [Math.floor(CONTENT_WIDTH_DXA / 2), Math.floor(CONTENT_WIDTH_DXA / 2)],
    borders: TableBorders.NONE,
    rows: [metaRow],
  }));

  elements.push(spacer(600));

  // Session ID footnote
  if (data.session_id) {
    elements.push(new Paragraph({
      children: [
        new TextRun({
          text: `Сессия: ${data.session_id}`,
          font: FONT,
          color: C.textMuted,
          size: 16,
          italics: true,
        }),
      ],
      spacing: { before: 0, after: 80 },
    }));
  }

  // Page break (cover → main)
  elements.push(pageBreak());

  return elements;
}

// ---------------------------------------------------------------------------
// Executive Summary
// ---------------------------------------------------------------------------

/**
 * buildExecutiveSummary(data) — Executive Summary section.
 * Includes: H1, KPI grid, Q&A items, ranking, gold callout.
 */
export function buildExecutiveSummary(data) {
  const elements = [];

  elements.push(H1("Аналитическое резюме"));

  // Main answer paragraph
  const mainAnswer = data.executive_summary?.main_answer ?? "";
  if (mainAnswer) {
    elements.push(P(parseInlineMarkdown(mainAnswer, { size: 22 }), {
      spacing: { after: 200 },
    }));
  }

  // KPI grid from key_numbers_highlight
  const kpiItems = data.key_numbers_highlight ?? [];
  if (kpiItems.length > 0) {
    elements.push(H2("Ключевые показатели"));

    // Build rows of 3
    for (let i = 0; i < kpiItems.length; i += 3) {
      const batch = kpiItems.slice(i, i + 3);
      elements.push(kpiRow(batch.map((k) => ({
        value: k.value,
        label: k.label,
        sublabel: k.source_ref ?? "",
      }))));
      elements.push(spacer(160));
    }

    // Fallback: use key_numbers from executive_summary if no key_numbers_highlight
  } else {
    const keyNums = data.executive_summary?.key_numbers ?? [];
    if (keyNums.length > 0) {
      elements.push(H2("Ключевые показатели"));
      for (let i = 0; i < keyNums.length; i += 3) {
        const batch = keyNums.slice(i, i + 3);
        elements.push(kpiRow(batch.map((k) => ({
          value: k.value,
          label: `${k.metric}${k.subject ? ` — ${k.subject}` : ""}`,
          sublabel: k.source_url ?? "",
        }))));
        elements.push(spacer(160));
      }
    }
  }

  // Q&A section
  const qaItems = data.qa_section ?? [];
  if (qaItems.length > 0) {
    elements.push(spacer(200));
    elements.push(H2("Ответы на ключевые вопросы"));

    qaItems.forEach((item) => {
      elements.push(new Paragraph({
        children: [
          new TextRun({ text: "В: ", font: FONT, bold: true, color: C.primary, size: 22 }),
          new TextRun({ text: item.question, font: FONT, bold: true, color: C.textDark, size: 22 }),
        ],
        spacing: { before: 200, after: 60 },
      }));
      elements.push(new Paragraph({
        children: [
          new TextRun({ text: "О: ", font: FONT, bold: true, color: C.accent, size: 22 }),
          new TextRun({ text: item.answer, font: FONT, color: C.textDark, size: 22 }),
        ],
        spacing: { before: 0, after: 60 },
      }));
      if (item.details_ref) {
        elements.push(new Paragraph({
          children: [
            new TextRun({
              text: `Подробнее: ${item.details_ref}`,
              font: FONT,
              italics: true,
              color: C.textMuted,
              size: 18,
            }),
          ],
          spacing: { before: 0, after: 80 },
        }));
      }
    });
  }

  // Ranking section
  const rankingItems = data.ranking ?? [];
  if (rankingItems.length > 0) {
    elements.push(spacer(200));
    elements.push(H2("Приоритизация"));

    // Build ranking table
    const hasWeight = rankingItems.some((r) => r.weight != null);
    const headers = hasWeight
      ? ["#", "Позиция", "Вес", "Обоснование", "Надёжность"]
      : ["#", "Позиция", "Обоснование", "Надёжность"];

    const widths = hasWeight
      ? [400, 2000, 600, 4360, 1200]
      : [400, 2400, 4760, 1200];

    const rows = rankingItems.map((item, idx) => {
      const strengthMap = { high: "Высокая", medium: "Средняя", low: "Низкая" };
      if (hasWeight) {
        return [
          String(idx + 1),
          item.label,
          item.weight != null ? String(item.weight) : "—",
          item.rationale,
          strengthMap[item.evidence_strength] ?? item.evidence_strength,
        ];
      }
      return [
        String(idx + 1),
        item.label,
        item.rationale,
        strengthMap[item.evidence_strength] ?? item.evidence_strength,
      ];
    });

    elements.push(dataTable(headers, rows, widths));
    elements.push(spacer(120));
  }

  // Top findings as numbered list
  const topFindings = data.executive_summary?.top_findings ?? [];
  if (topFindings.length > 0) {
    elements.push(spacer(200));
    elements.push(H2("Ключевые выводы"));
    topFindings.forEach((finding) => {
      elements.push(numbered(parseInlineMarkdown(finding, { size: 22 })));
    });
  }

  // Confidence note + what_meta_adds
  const confidenceNote = data.executive_summary?.confidence_note ?? "";
  const whatMetaAdds = data.executive_summary?.what_meta_adds ?? "";
  if (confidenceNote || whatMetaAdds) {
    elements.push(spacer(200));
    const bodyLines = [];
    if (confidenceNote) bodyLines.push(confidenceNote);
    if (whatMetaAdds) bodyLines.push(whatMetaAdds);
    elements.push(callout("Методологическая заметка", bodyLines, "gold"));
  }

  elements.push(spacer(200));
  elements.push(pageBreak());

  return elements;
}

// ---------------------------------------------------------------------------
// Table of Contents (static)
// ---------------------------------------------------------------------------

/**
 * buildTableOfContents(tocItems) — static TOC.
 * @param {Array<{title: string, level: number, page?: number}>} tocItems
 */
export function buildTableOfContents(tocItems) {
  const elements = [];

  elements.push(H1("Содержание"));

  tocItems.forEach((item) => {
    const indent = item.level === 2 ? 720 : item.level === 3 ? 1440 : 0;
    const fontSize = item.level === 1 ? 22 : 20;
    const bold = item.level === 1;

    elements.push(new Paragraph({
      children: [
        new TextRun({
          text: item.title,
          font: FONT,
          bold,
          color: bold ? C.primary : C.textDark,
          size: fontSize,
        }),
        ...(item.page != null ? [
          new TextRun({
            text: `\t${item.page}`,
            font: FONT,
            color: C.textMuted,
            size: fontSize,
          }),
        ] : []),
      ],
      indent: indent ? { left: indent } : undefined,
      spacing: { before: bold ? 120 : 60, after: bold ? 60 : 40 },
      tabStops: [{ type: "right", position: CONTENT_WIDTH_DXA }],
    }));
  });

  elements.push(spacer(200));
  elements.push(pageBreak());

  return elements;
}

// ---------------------------------------------------------------------------
// Main chapters from main_synthesis markdown
// ---------------------------------------------------------------------------

/**
 * buildMainChapters(data, chartDir) — parses main_synthesis and renders chapters.
 * Also embeds tables, charts, and callouts from structured fields.
 * @param {object} data — FinalReport JSON
 * @param {string|null} chartDir — path to directory with chart_NN.png files
 */
export function buildMainChapters(data, chartDir = null) {
  const elements = [];

  // Parse main_synthesis markdown
  const synthesis = data.main_synthesis ?? "";
  if (synthesis) {
    const blocks = parseMarkdownBlocks(synthesis);
    elements.push(...blocks);
  }

  // Embed structured tables
  const tables = data.tables ?? [];
  if (tables.length > 0) {
    elements.push(spacer(200));
    elements.push(H2("Аналитические таблицы"));

    tables.forEach((tbl, idx) => {
      elements.push(H3(tbl.title ?? `Таблица ${idx + 1}`));

      if (tbl.columns && tbl.rows) {
        const count = tbl.columns.length;
        const widths = tbl.columns.map(() => Math.floor(CONTENT_WIDTH_DXA / count));
        elements.push(dataTable(tbl.columns, tbl.rows, widths));
      }

      const captionParts = [];
      if (tbl.caption) captionParts.push(tbl.caption);
      if (tbl.source_ref) captionParts.push(`Источники: ${tbl.source_ref}`);
      if (captionParts.length > 0) {
        elements.push(caption(`Таблица ${idx + 1}. ${captionParts.join(" ")}`));
      }
      elements.push(spacer(120));
    });
  }

  // Embed charts (pre-rendered PNGs from chart_dir/chart_NN.png)
  const charts = data.charts ?? [];
  if (charts.length > 0 && chartDir) {
    elements.push(spacer(200));
    elements.push(H2("Диаграммы"));

    charts.forEach((chart, idx) => {
      const chartPath = path.join(chartDir, `chart_${String(idx).padStart(2, "0")}.png`);
      if (fs.existsSync(chartPath)) {
        const imgBlocks = embedImage(
          chartPath,
          6858000,  // ~75% of content width in EMU
          3858750,
          chart.caption ?? chart.title
        );
        elements.push(...imgBlocks);
      } else {
        // Placeholder if chart PNG not found
        elements.push(callout(
          `[${chart.chart_type.toUpperCase()}] ${chart.title}`,
          chart.caption ?? "График недоступен — PNG не найден",
          "note"
        ));
      }
      elements.push(spacer(120));
    });
  } else if (charts.length > 0) {
    // No chart_dir — render placeholders
    elements.push(spacer(200));
    charts.forEach((chart) => {
      elements.push(callout(
        `[${chart.chart_type.toUpperCase()}] ${chart.title}`,
        chart.caption ?? "",
        "note"
      ));
      elements.push(spacer(80));
    });
  }

  // Callout blocks
  const callouts = data.callouts ?? [];
  if (callouts.length > 0) {
    elements.push(spacer(200));
    elements.push(H2("Ключевые инсайты"));

    callouts.forEach((cb) => {
      const variantMap = {
        insight: "primary",
        warning: "warning",
        key_number: "gold",
        note: "note",
      };
      const variant = variantMap[cb.kind] ?? "primary";
      elements.push(callout(cb.title, cb.body, variant));
      elements.push(spacer(120));
    });
  }

  // Consensus section
  const consensusText = data.consensus_section ?? "";
  if (consensusText) {
    elements.push(spacer(200));
    elements.push(H2("Консенсус источников"));
    const blocks = parseMarkdownBlocks(consensusText);
    elements.push(...blocks);
  }

  // Conflicts section
  const conflictsText = data.conflicts_section ?? "";
  if (conflictsText) {
    elements.push(spacer(200));
    elements.push(H2("Расхождения между источниками"));
    const blocks = parseMarkdownBlocks(conflictsText);
    elements.push(...blocks);
    elements.push(callout(
      "Методология разрешения конфликтов",
      "При расхождении данных принималась более актуальная и методологически прозрачная цифра. Детали — выше.",
      "gold"
    ));
  }

  // Gaps filled
  const gapsText = data.gaps_filled_section ?? "";
  if (gapsText) {
    elements.push(spacer(200));
    elements.push(H2("Закрытые пробелы в данных"));
    const blocks = parseMarkdownBlocks(gapsText);
    elements.push(...blocks);
  }

  elements.push(spacer(200));
  elements.push(pageBreak());

  return elements;
}

// ---------------------------------------------------------------------------
// Sources section
// ---------------------------------------------------------------------------

/**
 * buildSourcesSection(sources) — numbered bibliography.
 * @param {Array<{title: string, url: string, tool: string, reliability: string}>} sources
 */
export function buildSourcesSection(sources) {
  const elements = [];

  elements.push(H1("Источники"));

  if (!sources || sources.length === 0) {
    elements.push(P("Источники не указаны.", { spacing: { after: 200 } }));
  } else {
    // Group by tool
    const toolGroups = {};
    sources.forEach((src) => {
      const tool = src.tool ?? "other";
      if (!toolGroups[tool]) toolGroups[tool] = [];
      toolGroups[tool].push(src);
    });

    const toolLabelMap = {
      perplexity: "Perplexity",
      openai_dr: "OpenAI Deep Research",
      claude: "Claude",
      other: "Другие источники",
    };

    let globalIdx = 1;

    Object.entries(toolGroups).forEach(([tool, toolSources]) => {
      const toolLabel = toolLabelMap[tool] ?? tool;
      elements.push(H2(toolLabel));

      toolSources.forEach((src) => {
        const relMap = { high: "★★★", medium: "★★☆", low: "★☆☆" };
        const relStr = relMap[src.reliability] ?? "";
        const urlPart = src.url ? ` — ${src.url}` : "";
        const text = `[${globalIdx}] ${src.title}${urlPart} ${relStr}`;

        elements.push(new Paragraph({
          children: [
            new TextRun({
              text: String(globalIdx),
              font: FONT,
              bold: true,
              color: C.primary,
              size: 20,
            }),
            new TextRun({ text: `. ${src.title}`, font: FONT, bold: false, color: C.textDark, size: 20 }),
            ...(src.url ? [
              new TextRun({ text: `\n   ${src.url}`, font: FONT, color: C.textMuted, size: 18, italics: true }),
            ] : []),
            ...(relStr ? [
              new TextRun({ text: `  ${relStr}`, font: FONT, color: C.accent, size: 18 }),
            ] : []),
          ],
          spacing: { before: 80, after: 80 },
          indent: { left: 360 },
        }));

        globalIdx++;
      });

      elements.push(spacer(120));
    });
  }

  // Methodology callout
  elements.push(spacer(200));
  elements.push(callout(
    "Методологическая заметка",
    [
      "Отчёт основан на мета-анализе нескольких независимых исследовательских источников.",
      "Система надёжности: ★★★ высокая, ★★☆ средняя, ★☆☆ низкая.",
      "Числовые показатели сопровождаются ссылками [N] на соответствующий источник.",
      "При расхождении данных между источниками принималась наиболее методологически обоснованная цифра.",
    ],
    "gold"
  ));

  return elements;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function truncateTitle(text, maxLen) {
  if (text.length <= maxLen) return text;
  return text.slice(0, maxLen - 3) + "...";
}

function formatDateRu(date) {
  const months = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
  ];
  return `${date.getDate()} ${months[date.getMonth()]} ${date.getFullYear()}`;
}

/**
 * extractTocItems(data) — builds TOC item list from main_synthesis headings + fixed sections.
 */
export function extractTocItems(data) {
  const items = [];

  // Fixed sections always present
  items.push({ title: "Аналитическое резюме", level: 1 });

  if ((data.qa_section ?? []).length > 0) {
    items.push({ title: "Ответы на ключевые вопросы", level: 2 });
  }
  if ((data.ranking ?? []).length > 0) {
    items.push({ title: "Приоритизация", level: 2 });
  }
  if ((data.executive_summary?.top_findings ?? []).length > 0) {
    items.push({ title: "Ключевые выводы", level: 2 });
  }

  // Parse headings from main_synthesis
  const synthesis = data.main_synthesis ?? "";
  synthesis.split("\n").forEach((line) => {
    const trimmed = line.trim();
    if (trimmed.startsWith("## ")) {
      items.push({ title: trimmed.slice(3).trim(), level: 1 });
    } else if (trimmed.startsWith("### ")) {
      items.push({ title: trimmed.slice(4).trim(), level: 2 });
    }
  });

  // Structured sections
  if ((data.tables ?? []).length > 0) {
    items.push({ title: "Аналитические таблицы", level: 1 });
  }
  if ((data.callouts ?? []).length > 0) {
    items.push({ title: "Ключевые инсайты", level: 1 });
  }
  if (data.consensus_section) {
    items.push({ title: "Консенсус источников", level: 1 });
  }
  if (data.conflicts_section) {
    items.push({ title: "Расхождения между источниками", level: 1 });
  }
  if (data.gaps_filled_section) {
    items.push({ title: "Закрытые пробелы в данных", level: 1 });
  }

  // Sources always last
  items.push({ title: "Источники", level: 1 });

  return items;
}
