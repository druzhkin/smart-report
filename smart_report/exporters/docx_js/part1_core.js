/**
 * part1_core.js — Design tokens, primitives, and reusable block builders.
 *
 * Exports: C (palette), P, R, H1, H2, H3, caption, spacer, hr,
 *          callout, kpiCard, kpiRow, dataTable, bullet, numbered.
 *
 * Critical constraints (methodology §10):
 *   - ShadingType.CLEAR with fill + color:"auto" — never SOLID
 *   - Column widths in DXA (US Letter, 1440 DXA margins = 9360 DXA available)
 *   - Bullets/numbered via numbering.config, not unicode •
 *   - PageBreak only inside new Paragraph({ children: [new PageBreak()] })
 *   - Russian quotes «» „", not ""
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
  VerticalAlign,
  WidthType,
} from "docx";
import fs from "fs";

// ---------------------------------------------------------------------------
// Design tokens — canonical palette (methodology §4)
// ---------------------------------------------------------------------------

export const C = {
  primary:     "1F3A5F",   // deep navy — headings, accents
  primaryDark: "14253D",
  accent:      "C9A961",   // gold/brass — premium accent
  accentSoft:  "F0E4C4",
  textDark:    "1A1A1A",
  textMuted:   "595959",
  bgLight:     "F5F2EC",
  bgCallout:   "EEF2F7",
  bgTable:     "F7F4ED",
  border:      "C8C8C8",
  success:     "2E7D4F",
  danger:      "A0321C",
};

// Fonts
const FONT = "Calibri";

// Page geometry: US Letter inside 1440 DXA margins
export const PAGE_WIDTH_DXA = 12240;
export const MARGIN_DXA = 1440;
export const CONTENT_WIDTH_DXA = PAGE_WIDTH_DXA - MARGIN_DXA * 2; // 9360

// ---------------------------------------------------------------------------
// Text run primitive
// ---------------------------------------------------------------------------

/**
 * R(text, opts) — creates a styled TextRun.
 * @param {string} text
 * @param {{ bold?: boolean, italic?: boolean, color?: string, size?: number, font?: string, underline?: boolean }} opts
 */
export function R(text, opts = {}) {
  return new TextRun({
    text,
    font: opts.font ?? FONT,
    bold: opts.bold ?? false,
    italics: opts.italic ?? false,
    color: opts.color ?? C.textDark,
    size: opts.size ?? 22,          // 11pt default
    underline: opts.underline ? {} : undefined,
  });
}

// ---------------------------------------------------------------------------
// Paragraph primitive
// ---------------------------------------------------------------------------

/**
 * P(textOrRuns, opts) — creates a styled Paragraph.
 * @param {string | TextRun | Array<TextRun>} textOrRuns
 * @param {{ spacing?: object, alignment?: string, indent?: object, numbering?: object, outlineLevel?: number }} opts
 */
export function P(textOrRuns, opts = {}) {
  const children = typeof textOrRuns === "string"
    ? [R(textOrRuns)]
    : Array.isArray(textOrRuns)
      ? textOrRuns
      : [textOrRuns];

  return new Paragraph({
    children,
    spacing: opts.spacing ?? { after: 120 },
    alignment: opts.alignment ?? AlignmentType.LEFT,
    indent: opts.indent,
    numbering: opts.numbering,
    outlineLevel: opts.outlineLevel,
  });
}

// ---------------------------------------------------------------------------
// Heading primitives
// ---------------------------------------------------------------------------

/**
 * H1(text, opts) — Heading level 1.
 * Large navy text, 32pt, bold.
 */
export function H1(text, opts = {}) {
  return new Paragraph({
    children: [
      new TextRun({
        text,
        font: FONT,
        bold: true,
        color: C.primary,
        size: 64,  // 32pt
      }),
    ],
    spacing: { before: 480, after: 200 },
    outlineLevel: 0,
    ...opts,
  });
}

/**
 * H2(text, opts) — Heading level 2.
 * Navy text, 26pt, bold.
 */
export function H2(text, opts = {}) {
  return new Paragraph({
    children: [
      new TextRun({
        text,
        font: FONT,
        bold: true,
        color: C.primary,
        size: 52,  // 26pt
      }),
    ],
    spacing: { before: 360, after: 160 },
    outlineLevel: 1,
    ...opts,
  });
}

/**
 * H3(text, opts) — Heading level 3.
 * Navy text, 22pt, bold.
 */
export function H3(text, opts = {}) {
  return new Paragraph({
    children: [
      new TextRun({
        text,
        font: FONT,
        bold: true,
        color: C.primary,
        size: 44,  // 22pt
      }),
    ],
    spacing: { before: 280, after: 120 },
    outlineLevel: 2,
    ...opts,
  });
}

// ---------------------------------------------------------------------------
// Caption, spacer, horizontal rule
// ---------------------------------------------------------------------------

/** caption(text) — small muted italic text for table/figure labels */
export function caption(text) {
  return new Paragraph({
    children: [
      new TextRun({
        text,
        font: FONT,
        italics: true,
        color: C.textMuted,
        size: 18,  // 9pt
      }),
    ],
    spacing: { before: 60, after: 200 },
  });
}

/** spacer(sizeDXA) — blank paragraph with given spacing */
export function spacer(sizeDXA = 200) {
  return new Paragraph({
    children: [],
    spacing: { before: 0, after: sizeDXA },
  });
}

/** hr(color, sizePoints) — horizontal rule as a paragraph border */
export function hr(color = C.border, sizePoints = 6) {
  return new Paragraph({
    children: [],
    border: {
      bottom: {
        color,
        style: BorderStyle.SINGLE,
        size: sizePoints,
        space: 1,
      },
    },
    spacing: { before: 120, after: 120 },
  });
}

/** pageBreak() — explicit page break */
export function pageBreak() {
  return new Paragraph({
    children: [
      new TextRun({ break: 1 }),
    ],
  });
}

// ---------------------------------------------------------------------------
// Callout block (single-cell table with colored left border)
// ---------------------------------------------------------------------------

/**
 * callout(title, lines, variant) — highlighted block.
 * variant: "primary" (navy bg) | "gold" (accent bg) | "warning" (danger) | "success"
 * @param {string} title
 * @param {string | string[]} lines — body text (single string or array of strings)
 * @param {"primary" | "gold" | "warning" | "success" | "note"} variant
 * @returns {Table}
 */
export function callout(title, lines, variant = "primary") {
  const linesArr = Array.isArray(lines) ? lines : [lines];

  const bgMap = {
    primary: C.bgCallout,
    gold: C.accentSoft,
    warning: "FFF3F3",
    success: "F0F8F3",
    note: C.bgLight,
  };
  const borderColorMap = {
    primary: C.primary,
    gold: C.accent,
    warning: C.danger,
    success: C.success,
    note: C.border,
  };

  const bg = bgMap[variant] ?? C.bgCallout;
  const borderColor = borderColorMap[variant] ?? C.primary;

  const titleRun = new TextRun({
    text: title,
    font: FONT,
    bold: true,
    color: borderColor,
    size: 22,
  });

  const bodyRuns = linesArr.map((line, idx) =>
    new TextRun({
      text: line,
      font: FONT,
      color: C.textDark,
      size: 20,
      break: idx > 0 ? 1 : 0,
    })
  );

  const cellParagraphs = [
    new Paragraph({
      children: [titleRun],
      spacing: { before: 0, after: 80 },
    }),
    new Paragraph({
      children: bodyRuns,
      spacing: { before: 0, after: 0 },
    }),
  ];

  return new Table({
    width: { size: CONTENT_WIDTH_DXA, type: WidthType.DXA },
    columnWidths: [CONTENT_WIDTH_DXA],
    borders: TableBorders.NONE,
    rows: [
      new TableRow({
        children: [
          new TableCell({
            width: { size: CONTENT_WIDTH_DXA, type: WidthType.DXA },
            shading: {
              type: ShadingType.CLEAR,
              fill: bg,
              color: "auto",
            },
            borders: {
              top: { style: BorderStyle.NONE, size: 0, color: "auto" },
              right: { style: BorderStyle.NONE, size: 0, color: "auto" },
              bottom: { style: BorderStyle.NONE, size: 0, color: "auto" },
              left: {
                style: BorderStyle.SINGLE,
                size: 32,
                color: borderColor,
              },
            },
            margins: {
              top: 120,
              bottom: 120,
              left: 200,
              right: 200,
            },
            children: cellParagraphs,
          }),
        ],
      }),
    ],
  });
}

// ---------------------------------------------------------------------------
// KPI card and KPI row (2×3 grid for executive summary)
// ---------------------------------------------------------------------------

/**
 * kpiCard(value, label, sublabel) — single KPI cell contents.
 * Returns a TableCell object for embedding in a row.
 * @param {string} value — e.g. "883.8 тыс."
 * @param {string} label — e.g. "руб./м² — Prime Park"
 * @param {string} [sublabel] — e.g. source reference
 * @param {number} [cellWidth] — DXA width of this cell
 */
export function kpiCard(value, label, sublabel = "", cellWidth = 3120) {
  const cleanValue = compactText(value, 28);
  const cleanLabel = compactText(label, 92);
  const cleanSublabel = compactText(sublabel, 64);

  return new TableCell({
    width: { size: cellWidth, type: WidthType.DXA },
    shading: {
      type: ShadingType.CLEAR,
      fill: C.bgLight,
      color: "auto",
    },
    borders: {
      top: { style: BorderStyle.SINGLE, size: 8, color: C.primary },
      bottom: { style: BorderStyle.SINGLE, size: 8, color: C.primary },
      left: { style: BorderStyle.SINGLE, size: 8, color: C.primary },
      right: { style: BorderStyle.SINGLE, size: 8, color: C.primary },
    },
    margins: { top: 120, bottom: 120, left: 160, right: 160 },
    verticalAlign: VerticalAlign.CENTER,
    children: [
      new Paragraph({
        children: [
          new TextRun({
            text: cleanValue,
            font: FONT,
            bold: true,
            color: C.primary,
            size: cleanValue.length > 14 ? 44 : 60,
          }),
        ],
        alignment: AlignmentType.CENTER,
        spacing: { before: 0, after: 60 },
      }),
      new Paragraph({
        children: [
          new TextRun({
            text: cleanLabel,
            font: FONT,
            color: C.textDark,
            size: 18,  // 9pt
          }),
        ],
        alignment: AlignmentType.CENTER,
        spacing: { before: 0, after: cleanSublabel ? 40 : 0 },
      }),
      ...(cleanSublabel ? [
        new Paragraph({
          children: [
            new TextRun({
              text: cleanSublabel,
              font: FONT,
              italics: true,
              color: C.textMuted,
              size: 16,  // 8pt
            }),
          ],
          alignment: AlignmentType.CENTER,
          spacing: { before: 0, after: 0 },
        }),
      ] : []),
    ],
  });
}

/**
 * kpiRow(cards) — builds a table row from an array of kpiCard cells.
 * Accepts up to 3 cards per row; auto-distributes width.
 * @param {Array<{value: string, label: string, sublabel?: string}>} cards
 * @returns {Table}
 */
export function kpiRow(cards) {
  const count = Math.min(cards.length, 3);
  // Gutter between cells: 120 DXA
  const gutterTotal = (count - 1) * 120;
  const cellWidth = Math.floor((CONTENT_WIDTH_DXA - gutterTotal) / count);
  const allWidths = Array.from({ length: count }, () => cellWidth);

  const cells = cards.slice(0, count).map(({ value, label, sublabel }, i) =>
    kpiCard(value, label, sublabel ?? "", allWidths[i])
  );

  return new Table({
    width: { size: CONTENT_WIDTH_DXA, type: WidthType.DXA },
    columnWidths: allWidths,
    borders: TableBorders.NONE,
    rows: [
      new TableRow({
        children: cells,
        height: { value: 1320, rule: HeightRule.AT_LEAST },
      }),
    ],
  });
}

// ---------------------------------------------------------------------------
// Data table with header row shading
// ---------------------------------------------------------------------------

/**
 * dataTable(headers, rows, columnWidthsDXA) — structured data table.
 * @param {string[]} headers
 * @param {Array<string[] | Array<{text: string, bold?: boolean, color?: string}>>} rows
 * @param {number[]} columnWidthsDXA — must sum to CONTENT_WIDTH_DXA
 * @returns {Table}
 */
export function dataTable(headers, rows, columnWidthsDXA) {
  // Default: equal widths
  const widths = columnWidthsDXA ?? headers.map(() =>
    Math.floor(CONTENT_WIDTH_DXA / headers.length)
  );

  const headerRow = new TableRow({
    tableHeader: true,
    children: headers.map((h, i) =>
      new TableCell({
        width: { size: widths[i], type: WidthType.DXA },
        shading: {
          type: ShadingType.CLEAR,
          fill: C.primary,
          color: "auto",
        },
        borders: {
          top: { style: BorderStyle.SINGLE, size: 4, color: C.primary },
          bottom: { style: BorderStyle.SINGLE, size: 4, color: C.primary },
          left: { style: BorderStyle.SINGLE, size: 4, color: C.primary },
          right: { style: BorderStyle.SINGLE, size: 4, color: C.primary },
        },
        margins: { top: 80, bottom: 80, left: 120, right: 120 },
        children: [
          new Paragraph({
            children: [
              new TextRun({
                text: compactText(h, 42),
                font: FONT,
                bold: true,
                color: "FFFFFF",
                size: 18,
              }),
            ],
            spacing: { before: 0, after: 0 },
          }),
        ],
      })
    ),
  });

  const dataRows = rows.map((row, rowIdx) => {
    const isEven = rowIdx % 2 === 0;
    const bg = isEven ? C.bgTable : "FFFFFF";

    return new TableRow({
      children: row.map((cell, colIdx) => {
        const cellText = compactText(typeof cell === "string" ? cell : cell.text, 180);
        const cellBold = typeof cell === "object" ? (cell.bold ?? false) : false;
        const cellColor = typeof cell === "object" ? (cell.color ?? C.textDark) : C.textDark;

        return new TableCell({
          width: { size: widths[colIdx], type: WidthType.DXA },
          shading: {
            type: ShadingType.CLEAR,
            fill: bg,
            color: "auto",
          },
          borders: {
            top: { style: BorderStyle.SINGLE, size: 2, color: C.border },
            bottom: { style: BorderStyle.SINGLE, size: 2, color: C.border },
            left: { style: BorderStyle.SINGLE, size: 2, color: C.border },
            right: { style: BorderStyle.SINGLE, size: 2, color: C.border },
          },
          margins: { top: 60, bottom: 60, left: 120, right: 120 },
          children: [
            new Paragraph({
              children: [
                new TextRun({
                  text: cellText,
                  font: FONT,
                  bold: cellBold,
                  color: cellColor,
                  size: 17,
                }),
              ],
              spacing: { before: 0, after: 0 },
            }),
          ],
        });
      }),
    });
  });

  return new Table({
    width: { size: CONTENT_WIDTH_DXA, type: WidthType.DXA },
    columnWidths: widths,
    rows: [headerRow, ...dataRows],
  });
}

function compactText(value, maxLen) {
  const text = String(value ?? "").replace(/\s+/g, " ").trim();
  if (text.length <= maxLen) return text;
  return text.slice(0, Math.max(0, maxLen - 1)).trimEnd() + "…";
}

// ---------------------------------------------------------------------------
// Bullet and numbered list items (via numbering.config — NOT unicode •)
// ---------------------------------------------------------------------------

/**
 * bullet(textOrRuns, level) — bulleted list item.
 * Uses the "bullets" numbering reference from main.js numbering config.
 * @param {string | TextRun[]} textOrRuns
 * @param {number} level — 0=top, 1=sub
 */
export function bullet(textOrRuns, level = 0) {
  const children = typeof textOrRuns === "string"
    ? [R(textOrRuns)]
    : Array.isArray(textOrRuns) ? textOrRuns : [textOrRuns];

  return new Paragraph({
    children,
    numbering: { reference: "bullets", level },
    spacing: { before: 60, after: 60 },
  });
}

/**
 * numbered(textOrRuns, level) — numbered list item (%1.).
 * Uses the "numbers" numbering reference from main.js numbering config.
 * @param {string | TextRun[]} textOrRuns
 * @param {number} level
 */
export function numbered(textOrRuns, level = 0) {
  const children = typeof textOrRuns === "string"
    ? [R(textOrRuns)]
    : Array.isArray(textOrRuns) ? textOrRuns : [textOrRuns];

  return new Paragraph({
    children,
    numbering: { reference: "numbers", level },
    spacing: { before: 60, after: 60 },
  });
}

// ---------------------------------------------------------------------------
// Image embed helper
// ---------------------------------------------------------------------------

/**
 * embedImage(imagePath, widthEmu, heightEmu) — embed a PNG/JPG image.
 * Returns a Paragraph containing an ImageRun.
 * @param {string} imagePath — absolute file path
 * @param {number} widthEmu — width in EMU (9144000 = full content width at 96dpi US Letter)
 * @param {number} heightEmu
 * @param {string} [captionText]
 * @returns {Paragraph[]}
 */
export function embedImage(imagePath, widthEmu = 6096000, heightEmu = 3429000, captionText = "") {
  const data = fs.readFileSync(imagePath);
  const ext = imagePath.toLowerCase().endsWith(".png") ? "png" : "jpg";

  const imgPara = new Paragraph({
    children: [
      new ImageRun({
        data,
        transformation: { width: Math.round(widthEmu / 9144), height: Math.round(heightEmu / 9144) },
        type: ext,
      }),
    ],
    alignment: AlignmentType.CENTER,
    spacing: { before: 120, after: 80 },
  });

  const result = [imgPara];
  if (captionText) {
    result.push(caption(captionText));
  }
  return result;
}

// ---------------------------------------------------------------------------
// Markdown inline parser — converts **bold** and *italic* runs
// ---------------------------------------------------------------------------

/**
 * parseInlineMarkdown(text, baseOpts) — parse **bold** and *italic* markers.
 * Returns an array of TextRun objects.
 * @param {string} text
 * @param {{ color?: string, size?: number }} baseOpts
 */
export function parseInlineMarkdown(text, baseOpts = {}) {
  const runs = [];
  // Match **bold**, *italic*, or plain text segments
  const pattern = /\*\*(.+?)\*\*|\*(.+?)\*|([^*]+)/g;
  let match;
  while ((match = pattern.exec(text)) !== null) {
    if (match[1] !== undefined) {
      runs.push(R(match[1], { ...baseOpts, bold: true }));
    } else if (match[2] !== undefined) {
      runs.push(R(match[2], { ...baseOpts, italic: true }));
    } else if (match[3] !== undefined) {
      runs.push(R(match[3], baseOpts));
    }
  }
  return runs.length ? runs : [R(text, baseOpts)];
}

// ---------------------------------------------------------------------------
// Markdown block parser — parses main_synthesis markdown into block elements
// ---------------------------------------------------------------------------

/**
 * parseMarkdownBlocks(markdown, opts) — converts markdown text to Paragraph[].
 * Handles: ## headings, ### headings, **bold** inline, bullet lists (- ), tables, plain paragraphs.
 * @param {string} markdown
 * @param {{ bulletRef?: string, numberedRef?: string }} opts
 * @returns {Array<Paragraph | Table>}
 */
export function parseMarkdownBlocks(markdown, opts = {}) {
  const lines = markdown.split("\n");
  const elements = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();

    // Skip empty lines
    if (!trimmed) {
      i++;
      continue;
    }

    // ## H2 heading
    if (trimmed.startsWith("## ")) {
      elements.push(H2(trimmed.slice(3).trim()));
      i++;
      continue;
    }

    // ### H3 heading
    if (trimmed.startsWith("### ")) {
      elements.push(H3(trimmed.slice(4).trim()));
      i++;
      continue;
    }

    // # H1 heading
    if (trimmed.startsWith("# ")) {
      elements.push(H1(trimmed.slice(2).trim()));
      i++;
      continue;
    }

    // Bullet list item (- or *)
    if (trimmed.startsWith("- ") || trimmed.startsWith("* ")) {
      const text = trimmed.slice(2).trim();
      const runs = parseInlineMarkdown(text);
      elements.push(bullet(runs));
      i++;
      continue;
    }

    // Markdown pipe table — collect all rows, build dataTable
    if (trimmed.startsWith("|")) {
      const tableLines = [];
      while (i < lines.length && lines[i].trim().startsWith("|")) {
        tableLines.push(lines[i].trim());
        i++;
      }
      const parsed = parseMarkdownTable(tableLines);
      if (parsed) {
        elements.push(parsed);
      }
      continue;
    }

    // Plain paragraph (may contain inline markdown)
    const runs = parseInlineMarkdown(trimmed);
    elements.push(P(runs, { spacing: { after: 160 } }));
    i++;
  }

  return elements;
}

/**
 * parseMarkdownTable(tableLines) — converts markdown pipe table lines to dataTable.
 * @param {string[]} tableLines
 * @returns {Table | null}
 */
function parseMarkdownTable(tableLines) {
  if (tableLines.length < 3) return null;

  const parseRow = (line) =>
    line.replace(/^\||\|$/g, "").split("|").map((cell) => cell.trim());

  const headers = parseRow(tableLines[0]);
  // tableLines[1] is the separator row (---|---|...)
  const dataRows = tableLines.slice(2).map(parseRow);

  // Compute widths proportionally based on header count
  const count = headers.length;
  const widths = headers.map(() => Math.floor(CONTENT_WIDTH_DXA / count));

  return dataTable(headers, dataRows, widths);
}
