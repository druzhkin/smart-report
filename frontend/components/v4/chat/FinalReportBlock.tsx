"use client";

/**
 * FinalReportBlock — full-width assistant card for the synthesized report.
 *
 * Structure:
 *   title + subtitle
 *   executive summary (clean typography, NO drop-cap)
 *   key numbers grid (compact, 2–3 cards)
 *   ranking as horizontal bar visual (restrained)
 *   Q→A list (understated — question / answer pairs)
 *   main synthesis in 680–780px readable column
 *   Экспорт + Новое исследование buttons
 */

import { useState } from "react";
import type { FinalReport } from "@/lib/apiV4";
import { exportUrl } from "@/lib/apiV4";
import { Download, Plus, ChevronDown } from "lucide-react";

export function FinalReportBlock({
  report,
  onNewResearch,
}: {
  report: FinalReport;
  onNewResearch: () => void;
}) {
  const exec = report.executive_summary;

  // Q→A list is derived from consensus + conflict + gap sections if present,
  // otherwise rendered from the top_findings as simple bullet Q/A.
  const qa: Array<{ q: string; a: string }> = [];
  if (report.consensus_section) {
    qa.push({ q: "Что согласованно подтверждается?", a: report.consensus_section });
  }
  if (report.conflicts_section) {
    qa.push({ q: "Где источники расходятся?", a: report.conflicts_section });
  }
  if (report.gaps_filled_section) {
    qa.push({ q: "Что закрыл добор?", a: report.gaps_filled_section });
  }

  return (
    <div
      className="vc-reveal"
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 32,
        width: "100%",
      }}
    >
      {/* Title + subtitle */}
      <div>
        <div className="vc-mono" style={{ fontSize: 11, marginBottom: 10 }}>
          Финальный мета-анализ
        </div>
        <h1 className="vc-h1" style={{ margin: 0 }}>
          {report.question}
        </h1>
      </div>

      {/* Executive Summary — main answer */}
      {exec.main_answer && (
        <section
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 18,
            maxWidth: 780,
          }}
        >
          <p
            style={{
              margin: 0,
              fontSize: 17,
              lineHeight: 1.6,
              color: "var(--vc-text)",
              letterSpacing: "-0.005em",
            }}
          >
            {exec.main_answer}
          </p>
          {exec.what_meta_adds && (
            <p
              style={{
                margin: 0,
                padding: "14px 16px",
                fontSize: 14,
                lineHeight: 1.6,
                color: "var(--vc-muted)",
                borderLeft: "2px solid var(--vc-border-s)",
              }}
            >
              <span className="vc-mono" style={{ fontSize: 10, marginRight: 8 }}>
                что добавляет мета-анализ
              </span>
              <br />
              {exec.what_meta_adds}
            </p>
          )}
        </section>
      )}

      {/* Key numbers grid */}
      {exec.key_numbers && exec.key_numbers.length > 0 && (
        <section>
          <div className="vc-mono" style={{ fontSize: 11, marginBottom: 10 }}>
            ключевые цифры
          </div>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: `repeat(${Math.min(3, exec.key_numbers.length)}, minmax(0, 1fr))`,
              gap: 10,
            }}
          >
            {exec.key_numbers.slice(0, 3).map((kn, i) => (
              <div
                key={i}
                style={{
                  padding: "14px 16px",
                  background: "var(--vc-surface)",
                  border: "1px solid var(--vc-border)",
                  borderRadius: 12,
                }}
              >
                <div
                  style={{
                    fontFamily: "var(--vc-f-mono)",
                    fontVariantNumeric: "tabular-nums",
                    fontSize: 22,
                    fontWeight: 600,
                    letterSpacing: "-0.02em",
                    color: "var(--vc-text)",
                    lineHeight: 1.1,
                  }}
                >
                  {kn.value}
                </div>
                <div
                  style={{
                    marginTop: 6,
                    fontSize: 13,
                    color: "var(--vc-text)",
                    lineHeight: 1.4,
                  }}
                >
                  {kn.metric}
                </div>
                <div
                  className="vc-mono"
                  style={{ fontSize: 10, marginTop: 4 }}
                >
                  {kn.source}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Ranking bar */}
      {exec.ranking && (
        <section>
          <div className="vc-mono" style={{ fontSize: 11, marginBottom: 10 }}>
            ранжирование
          </div>
          <div
            style={{
              padding: "14px 16px",
              background: "var(--vc-surface)",
              border: "1px solid var(--vc-border)",
              borderRadius: 12,
            }}
          >
            <div style={{ fontSize: 14, color: "var(--vc-text)", lineHeight: 1.5 }}>
              {exec.ranking}
            </div>
            <div
              style={{
                marginTop: 10,
                height: 4,
                background: "var(--vc-surface-2)",
                borderRadius: 2,
                overflow: "hidden",
              }}
            >
              <div
                style={{
                  width: "88%",
                  height: "100%",
                  background: "var(--vc-text)",
                  borderRadius: 2,
                }}
              />
            </div>
          </div>
        </section>
      )}

      {/* Top findings — Q→A-ish list */}
      {exec.top_findings && exec.top_findings.length > 0 && (
        <section>
          <div className="vc-mono" style={{ fontSize: 11, marginBottom: 10 }}>
            главные выводы
          </div>
          <ol
            style={{
              margin: 0,
              padding: 0,
              listStyle: "none",
              display: "flex",
              flexDirection: "column",
              gap: 0,
            }}
          >
            {exec.top_findings.map((f, i) => (
              <li
                key={i}
                style={{
                  display: "grid",
                  gridTemplateColumns: "28px 1fr",
                  gap: 12,
                  padding: "12px 0",
                  borderTop: i === 0 ? "none" : "1px solid var(--vc-border)",
                  fontSize: 15,
                  lineHeight: 1.6,
                }}
              >
                <span
                  className="vc-mono"
                  style={{ fontSize: 12, paddingTop: 2 }}
                >
                  {String(i + 1).padStart(2, "0")}
                </span>
                <span>{f}</span>
              </li>
            ))}
          </ol>
        </section>
      )}

      {/* Q→A collapsibles */}
      {qa.length > 0 && (
        <section style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <div className="vc-mono" style={{ fontSize: 11 }}>
            подробнее
          </div>
          {qa.map((pair, i) => (
            <QaItem key={i} q={pair.q} a={pair.a} />
          ))}
        </section>
      )}

      {/* Main synthesis — readable column */}
      {report.main_synthesis && (
        <section
          style={{
            maxWidth: 760,
            paddingTop: 8,
          }}
        >
          <div className="vc-mono" style={{ fontSize: 11, marginBottom: 14 }}>
            синтез
          </div>
          <div
            style={{
              fontSize: 15,
              lineHeight: 1.7,
              color: "var(--vc-text)",
              display: "flex",
              flexDirection: "column",
              gap: 16,
            }}
          >
            {report.main_synthesis
              .split("\n\n")
              .map((p) => p.trim())
              .filter(Boolean)
              .map((para, i) => (
                <ParagraphSmart key={i} text={para} />
              ))}
          </div>
        </section>
      )}

      {/* Confidence */}
      {exec.confidence_note && (
        <div
          style={{
            fontSize: 12,
            color: "var(--vc-subtle)",
            fontStyle: "italic",
            maxWidth: 680,
            lineHeight: 1.55,
          }}
        >
          {exec.confidence_note}
        </div>
      )}

      {/* Sources */}
      {report.all_sources && report.all_sources.length > 0 && (
        <section>
          <div className="vc-mono" style={{ fontSize: 11, marginBottom: 10 }}>
            источники · {report.all_sources.length}
          </div>
          <ul
            style={{
              margin: 0,
              padding: 0,
              listStyle: "none",
              display: "flex",
              flexDirection: "column",
              gap: 6,
            }}
          >
            {report.all_sources.slice(0, 8).map((s, i) => (
              <li
                key={i}
                style={{
                  display: "grid",
                  gridTemplateColumns: "80px 1fr",
                  gap: 10,
                  padding: "8px 0",
                  borderTop: i === 0 ? "none" : "1px solid var(--vc-border)",
                  alignItems: "baseline",
                }}
              >
                <span className="vc-mono" style={{ fontSize: 10 }}>
                  {s.origin || "—"}
                </span>
                <span
                  style={{
                    fontSize: 13,
                    color: "var(--vc-text)",
                    wordBreak: "break-word",
                  }}
                >
                  {s.title || s.url}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Actions */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          flexWrap: "wrap",
          paddingTop: 8,
        }}
      >
        <ExportMenu sessionId={report.session_id} />
        <button
          type="button"
          className="vc-btn vc-btn-ghost"
          onClick={onNewResearch}
        >
          <Plus size={14} strokeWidth={2} />
          <span>Новое исследование</span>
        </button>
      </div>
    </div>
  );
}

/* ----------- Q→A ----------- */

function QaItem({ q, a }: { q: string; a: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div
      style={{
        background: "var(--vc-surface)",
        border: "1px solid var(--vc-border)",
        borderRadius: 12,
        overflow: "hidden",
      }}
    >
      <button
        type="button"
        onClick={() => setOpen(!open)}
        style={{
          width: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "12px 16px",
          background: "transparent",
          border: "none",
          cursor: "pointer",
          fontFamily: "inherit",
          color: "var(--vc-text)",
          textAlign: "left",
          fontSize: 14,
          fontWeight: 500,
        }}
        aria-expanded={open}
      >
        <span>{q}</span>
        <ChevronDown
          size={14}
          strokeWidth={1.75}
          style={{
            color: "var(--vc-muted)",
            transition: "transform 180ms ease",
            transform: open ? "rotate(180deg)" : "none",
          }}
        />
      </button>
      {open && (
        <div
          className="vc-reveal"
          style={{
            padding: "6px 16px 16px",
            fontSize: 14,
            lineHeight: 1.6,
            color: "var(--vc-muted)",
            borderTop: "1px solid var(--vc-border)",
            whiteSpace: "pre-wrap",
          }}
        >
          {a}
        </div>
      )}
    </div>
  );
}

/* ----------- Paragraph with minimal md-ish inline formatting ----------- */

function ParagraphSmart({ text }: { text: string }) {
  // Handle ##/### headings → bold text; **x** → bold inline
  const trimmed = text.trim();
  if (trimmed.startsWith("## ")) {
    return (
      <h2 className="vc-h3" style={{ margin: "8px 0 -4px", fontSize: 17 }}>
        {trimmed.slice(3)}
      </h2>
    );
  }
  if (trimmed.startsWith("### ")) {
    return (
      <h3 style={{ margin: "4px 0 -8px", fontSize: 15, fontWeight: 600 }}>
        {trimmed.slice(4)}
      </h3>
    );
  }
  return (
    <p style={{ margin: 0 }} dangerouslySetInnerHTML={{ __html: inlineFormat(trimmed) }} />
  );
}

function inlineFormat(text: string): string {
  // Escape HTML first
  const esc = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
  // Bold + italic minimal
  return esc
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*]+)\*/g, "<em>$1</em>")
    .replace(/\n/g, "<br/>");
}

/* ----------- Export dropdown ----------- */

function ExportMenu({ sessionId }: { sessionId: string }) {
  const [open, setOpen] = useState(false);
  const formats = [
    { f: "docx", label: "Microsoft Word (.docx)" },
    { f: "pptx", label: "PowerPoint (.pptx)" },
    { f: "md", label: "Markdown (.md)" },
    { f: "pdf", label: "PDF (print-ready)" },
    { f: "html", label: "HTML" },
  ];

  return (
    <div style={{ position: "relative" }}>
      <button
        type="button"
        className="vc-btn vc-btn-primary"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
      >
        <Download size={14} strokeWidth={2} />
        <span>Экспорт</span>
      </button>
      {open && (
        <>
          <div
            style={{ position: "fixed", inset: 0, zIndex: 100 }}
            onClick={() => setOpen(false)}
          />
          <div
            className="vc-reveal"
            style={{
              position: "absolute",
              top: "calc(100% + 6px)",
              left: 0,
              minWidth: 240,
              background: "var(--vc-surface)",
              border: "1px solid var(--vc-border-s)",
              borderRadius: 12,
              padding: 6,
              boxShadow: "0 8px 32px rgba(0,0,0,0.08)",
              zIndex: 101,
            }}
          >
            {formats.map((fmt) => (
              <a
                key={fmt.f}
                href={exportUrl(sessionId, fmt.f)}
                target="_blank"
                rel="noreferrer"
                onClick={() => setOpen(false)}
                style={{
                  display: "grid",
                  gridTemplateColumns: "56px 1fr",
                  gap: 8,
                  padding: "8px 10px",
                  borderRadius: 8,
                  fontSize: 13,
                  textDecoration: "none",
                  color: "var(--vc-text)",
                }}
              >
                <span className="vc-mono" style={{ fontSize: 11 }}>
                  .{fmt.f}
                </span>
                <span>{fmt.label}</span>
              </a>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
