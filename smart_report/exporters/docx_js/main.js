/**
 * main.js — Document assembler for the DOCX v2 consulting renderer.
 *
 * Usage:
 *   node main.js <input.json> <output.docx> [--chart-dir <path>]
 *
 * input.json  — FinalReport serialized to JSON (see smart_report/models.py)
 * output.docx — path to write the resulting DOCX file
 * --chart-dir — optional path to directory with pre-rendered chart PNGs:
 *               chart_00.png, chart_01.png, …
 *
 * Document structure (methodology §6):
 *   Section 1: Cover page — no headers/footers
 *   Section 2: Main body — header (title + gold hairline), footer (author + page №)
 *     → Executive Summary (KPI grid, Q&A, ranking)
 *     → Static TOC
 *     → Main chapters (main_synthesis parsed + tables + charts + callouts)
 *     → Sources
 *
 * Exit codes:
 *   0 — success
 *   1 — bad arguments / file not found
 *   2 — render error (written to stderr)
 */

import {
  AlignmentType,
  Document,
  Footer,
  Header,
  LevelFormat,
  PageNumber,
  PageOrientation,
  Paragraph,
  SectionType,
  TabStopPosition,
  TabStopType,
  TextRun,
  convertInchesToTwip,
} from "docx";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { Packer } from "docx";

import { C, CONTENT_WIDTH_DXA, MARGIN_DXA, pageBreak } from "./part1_core.js";
import {
  buildCoverPage,
  buildExecutiveSummary,
  buildMainChapters,
  buildSourcesSection,
  buildTableOfContents,
  extractTocItems,
} from "./part2_sections.js";

const FONT = "Calibri";

// ---------------------------------------------------------------------------
// Argument parsing
// ---------------------------------------------------------------------------

const args = process.argv.slice(2);

if (args.length < 2) {
  console.error("Usage: node main.js <input.json> <output.docx> [--chart-dir <path>]");
  process.exit(1);
}

const inputJsonPath = path.resolve(args[0]);
const outputDocxPath = path.resolve(args[1]);

let chartDir = null;
const chartDirIdx = args.indexOf("--chart-dir");
if (chartDirIdx !== -1 && args[chartDirIdx + 1]) {
  chartDir = path.resolve(args[chartDirIdx + 1]);
}

// ---------------------------------------------------------------------------
// Load input JSON
// ---------------------------------------------------------------------------

if (!fs.existsSync(inputJsonPath)) {
  console.error(`Input file not found: ${inputJsonPath}`);
  process.exit(1);
}

let data;
try {
  data = JSON.parse(fs.readFileSync(inputJsonPath, "utf-8"));
} catch (err) {
  console.error(`Failed to parse input JSON: ${err.message}`);
  process.exit(1);
}

// ---------------------------------------------------------------------------
// Numbering config (methodology §7 — bullets/numbers via config, not unicode)
// ---------------------------------------------------------------------------

const numberingConfig = {
  config: [
    {
      reference: "bullets",
      levels: [
        {
          level: 0,
          format: LevelFormat.BULLET,
          text: "\u2022",
          alignment: AlignmentType.LEFT,
          style: {
            paragraph: {
              indent: { left: 720, hanging: 360 },
              spacing: { before: 60, after: 60 },
            },
            run: {
              font: FONT,
              size: 22,
            },
          },
        },
        {
          level: 1,
          format: LevelFormat.BULLET,
          text: "\u25E6",
          alignment: AlignmentType.LEFT,
          style: {
            paragraph: {
              indent: { left: 1440, hanging: 360 },
              spacing: { before: 40, after: 40 },
            },
            run: {
              font: FONT,
              size: 20,
            },
          },
        },
      ],
    },
    {
      reference: "numbers",
      levels: [
        {
          level: 0,
          format: LevelFormat.DECIMAL,
          text: "%1.",
          alignment: AlignmentType.LEFT,
          style: {
            paragraph: {
              indent: { left: 720, hanging: 360 },
              spacing: { before: 60, after: 60 },
            },
            run: {
              font: FONT,
              size: 22,
            },
          },
        },
        {
          level: 1,
          format: LevelFormat.LOWER_LETTER,
          text: "%2)",
          alignment: AlignmentType.LEFT,
          style: {
            paragraph: {
              indent: { left: 1440, hanging: 360 },
              spacing: { before: 40, after: 40 },
            },
            run: {
              font: FONT,
              size: 20,
            },
          },
        },
      ],
    },
  ],
};

// ---------------------------------------------------------------------------
// Paragraph styles override
// ---------------------------------------------------------------------------

const stylesConfig = {
  paragraphStyles: [
    {
      id: "Heading1",
      name: "heading 1",
      basedOn: "Normal",
      next: "Normal",
      quickFormat: true,
      run: {
        font: FONT,
        size: 64,
        bold: true,
        color: C.primary,
      },
      paragraph: {
        spacing: { before: 480, after: 200 },
        outlineLevel: 0,
      },
    },
    {
      id: "Heading2",
      name: "heading 2",
      basedOn: "Normal",
      next: "Normal",
      quickFormat: true,
      run: {
        font: FONT,
        size: 52,
        bold: true,
        color: C.primary,
      },
      paragraph: {
        spacing: { before: 360, after: 160 },
        outlineLevel: 1,
      },
    },
    {
      id: "Heading3",
      name: "heading 3",
      basedOn: "Normal",
      next: "Normal",
      quickFormat: true,
      run: {
        font: FONT,
        size: 44,
        bold: true,
        color: C.primary,
      },
      paragraph: {
        spacing: { before: 280, after: 120 },
        outlineLevel: 2,
      },
    },
    {
      id: "Normal",
      name: "Normal",
      run: {
        font: FONT,
        size: 22,
        color: C.textDark,
      },
      paragraph: {
        spacing: { after: 120 },
      },
    },
  ],
};

// ---------------------------------------------------------------------------
// Header and footer builders (Section 2)
// ---------------------------------------------------------------------------

function buildHeader(titleText) {
  const shortTitle = titleText.length > 60 ? titleText.slice(0, 57) + "..." : titleText;
  return new Header({
    children: [
      new Paragraph({
        children: [
          new TextRun({
            text: shortTitle,
            font: FONT,
            color: C.textMuted,
            size: 18,
          }),
        ],
        border: {
          bottom: {
            color: C.accent,
            style: "single",
            size: 6,
            space: 1,
          },
        },
        spacing: { before: 0, after: 120 },
      }),
    ],
  });
}

function buildFooter(authorText) {
  return new Footer({
    children: [
      new Paragraph({
        children: [
          new TextRun({
            text: authorText,
            font: FONT,
            color: C.textMuted,
            size: 18,
          }),
          new TextRun({
            children: ["\t", PageNumber.CURRENT],
            font: FONT,
            color: C.textMuted,
            size: 18,
          }),
        ],
        tabStops: [
          {
            type: TabStopType.RIGHT,
            position: CONTENT_WIDTH_DXA,
          },
        ],
        border: {
          top: {
            color: C.border,
            style: "single",
            size: 4,
            space: 1,
          },
        },
        spacing: { before: 80, after: 0 },
      }),
    ],
  });
}

// ---------------------------------------------------------------------------
// Assemble document
// ---------------------------------------------------------------------------

async function render() {
  const titleText = data.question ?? "Аналитический отчёт";
  const authorText = "Smart Report AI";

  // --- Section 1: Cover (no headers/footers) ---
  const coverChildren = buildCoverPage(data);

  // --- Section 2: Main body ---
  const tocItems = extractTocItems(data);

  const mainChildren = [
    ...buildExecutiveSummary(data),
    ...buildTableOfContents(tocItems),
    ...buildMainChapters(data, chartDir),
    ...buildSourcesSection(data.all_sources ?? []),
  ];

  const doc = new Document({
    numbering: numberingConfig,
    styles: stylesConfig,
    sections: [
      // Cover section — no headers/footers, no page numbers
      {
        properties: {
          type: SectionType.NEXT_PAGE,
          page: {
            margin: {
              top: MARGIN_DXA,
              right: MARGIN_DXA,
              bottom: MARGIN_DXA,
              left: MARGIN_DXA,
            },
            size: {
              orientation: PageOrientation.PORTRAIT,
              width: 12240,   // US Letter
              height: 15840,
            },
          },
        },
        children: coverChildren,
      },
      // Main section — with headers/footers
      {
        properties: {
          type: SectionType.CONTINUOUS,
          page: {
            margin: {
              top: MARGIN_DXA,
              right: MARGIN_DXA,
              bottom: MARGIN_DXA,
              left: MARGIN_DXA,
            },
            size: {
              orientation: PageOrientation.PORTRAIT,
              width: 12240,
              height: 15840,
            },
            pageNumbers: {
              start: 1,
            },
          },
        },
        headers: {
          default: buildHeader(titleText),
        },
        footers: {
          default: buildFooter(authorText),
        },
        children: mainChildren,
      },
    ],
  });

  // Write DOCX to disk
  const buffer = await Packer.toBuffer(doc);
  fs.writeFileSync(outputDocxPath, buffer);

  console.log(`OK: ${outputDocxPath} (${Math.round(buffer.length / 1024)} KB)`);
}

render().catch((err) => {
  console.error(`Render error: ${err.message}`);
  console.error(err.stack);
  process.exit(2);
});
