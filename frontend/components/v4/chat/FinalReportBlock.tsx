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
import type { AnalyticClosureReport, AnalyticDepthPlan, FinalReport } from "@/lib/apiV4";
import {
  exportUrl,
  generateGammaPptx,
  getAnalyticClosureReport,
  getAnalyticDepthPlan,
} from "@/lib/apiV4";
import { Activity, BrainCircuit, Download, Plus, ChevronDown } from "lucide-react";

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
        <AnalyticDepthMenu sessionId={report.session_id} />
        <AnalyticClosureMenu sessionId={report.session_id} />
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

function AnalyticClosureMenu({ sessionId }: { sessionId: string }) {
  const [open, setOpen] = useState(false);
  const [closure, setClosure] = useState<AnalyticClosureReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function toggle() {
    const nextOpen = !open;
    setOpen(nextOpen);
    if (!nextOpen || closure || loading) return;
    setLoading(true);
    setError(null);
    try {
      setClosure(await getAnalyticClosureReport(sessionId));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ position: "relative" }}>
      <button
        type="button"
        className="vc-btn vc-btn-ghost"
        onClick={toggle}
        aria-expanded={open}
        title="Show whether follow-up research closed the analytic leads"
      >
        <Activity size={14} strokeWidth={2} />
        <span>Closure score</span>
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
              width: "min(560px, calc(100vw - 32px))",
              maxHeight: "70vh",
              overflow: "auto",
              background: "var(--vc-surface)",
              border: "1px solid var(--vc-border-s)",
              borderRadius: 12,
              padding: 14,
              boxShadow: "0 8px 32px rgba(0,0,0,0.08)",
              zIndex: 101,
            }}
          >
            <div className="vc-mono" style={{ fontSize: 10, marginBottom: 8 }}>
              analytic follow-up closure
            </div>
            {loading && (
              <div style={{ fontSize: 13, color: "var(--vc-muted)" }}>
                Scoring whether follow-up reports close the priority research leads...
              </div>
            )}
            {error && (
              <div style={{ fontSize: 13, color: "var(--vc-warning, #b54708)" }}>
                {error}
              </div>
            )}
            {closure && (
              <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                <div>
                  <div style={{ fontSize: 26, fontWeight: 700 }}>
                    {closure.overall_score}/100
                  </div>
                  <div style={{ fontSize: 12, color: "var(--vc-muted)", lineHeight: 1.5 }}>
                    {closure.summary}
                  </div>
                </div>
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(4, minmax(0, 1fr))",
                    gap: 8,
                  }}
                >
                  {[
                    ["Closed", closure.closed],
                    ["Partial", closure.partial],
                    ["Open", closure.not_closed],
                    ["Not started", closure.not_started],
                  ].map(([label, value]) => (
                    <div
                      key={label}
                      style={{
                        border: "1px solid var(--vc-border-s)",
                        borderRadius: 8,
                        padding: "8px 10px",
                      }}
                    >
                      <div className="vc-mono" style={{ fontSize: 9 }}>{label}</div>
                      <div style={{ fontSize: 18, fontWeight: 650 }}>{value}</div>
                    </div>
                  ))}
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {closure.lead_closures.slice(0, 5).map((lead) => (
                    <div
                      key={lead.lead_id}
                      style={{
                        border: "1px solid var(--vc-border-s)",
                        borderRadius: 8,
                        padding: "9px 10px",
                      }}
                    >
                      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 4 }}>
                        <span className="vc-mono" style={{ fontSize: 9 }}>{lead.status}</span>
                        <span className="vc-mono" style={{ fontSize: 9 }}>{lead.kind}</span>
                        <span className="vc-mono" style={{ fontSize: 9 }}>{lead.score}/100</span>
                      </div>
                      <div style={{ fontSize: 12, lineHeight: 1.45 }}>
                        {lead.recommendation}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

function AnalyticDepthMenu({ sessionId }: { sessionId: string }) {
  const [open, setOpen] = useState(false);
  const [plan, setPlan] = useState<AnalyticDepthPlan | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function toggle() {
    const nextOpen = !open;
    setOpen(nextOpen);
    if (!nextOpen || plan || loading) return;
    setLoading(true);
    setError(null);
    try {
      setPlan(await getAnalyticDepthPlan(sessionId));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ position: "relative" }}>
      <button
        type="button"
        className="vc-btn vc-btn-ghost"
        onClick={toggle}
        aria-expanded={open}
        title="Show the investigation map behind the report"
      >
        <BrainCircuit size={14} strokeWidth={2} />
        <span>Analytic map</span>
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
              width: "min(560px, calc(100vw - 32px))",
              maxHeight: "70vh",
              overflow: "auto",
              background: "var(--vc-surface)",
              border: "1px solid var(--vc-border-s)",
              borderRadius: 12,
              padding: 14,
              boxShadow: "0 8px 32px rgba(0,0,0,0.08)",
              zIndex: 101,
            }}
          >
            <div className="vc-mono" style={{ fontSize: 10, marginBottom: 8 }}>
              deep analytical layer
            </div>
            {loading && (
              <div style={{ fontSize: 13, color: "var(--vc-muted)" }}>
                Building the issue tree, hypotheses, probes, and follow-up leads...
              </div>
            )}
            {error && (
              <div style={{ fontSize: 13, color: "var(--vc-warning, #b54708)" }}>
                {error}
              </div>
            )}
            {plan && (
              <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>
                    {plan.root.question}
                  </div>
                  <div style={{ fontSize: 12, color: "var(--vc-muted)", lineHeight: 1.5 }}>
                    Domain: {plan.domain_hint}. {plan.root.rationale}
                  </div>
                </div>

                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(4, minmax(0, 1fr))",
                    gap: 8,
                  }}
                >
                  {[
                    ["Branches", plan.root.children.length],
                    ["Hypotheses", plan.hypotheses.length],
                    ["Probes", plan.evidence_probes.length],
                    ["Leads", plan.research_leads.length],
                  ].map(([label, value]) => (
                    <div
                      key={label}
                      style={{
                        border: "1px solid var(--vc-border-s)",
                        borderRadius: 8,
                        padding: "8px 10px",
                      }}
                    >
                      <div className="vc-mono" style={{ fontSize: 9 }}>{label}</div>
                      <div style={{ fontSize: 18, fontWeight: 650 }}>{value}</div>
                    </div>
                  ))}
                </div>

                <div>
                  <div className="vc-mono" style={{ fontSize: 10, marginBottom: 6 }}>
                    priority research leads
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {plan.research_leads.slice(0, 5).map((lead) => (
                      <div
                        key={lead.id}
                        style={{
                          border: "1px solid var(--vc-border-s)",
                          borderRadius: 8,
                          padding: "9px 10px",
                        }}
                      >
                        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 4 }}>
                          <span className="vc-mono" style={{ fontSize: 9 }}>{lead.priority}</span>
                          <span className="vc-mono" style={{ fontSize: 9 }}>{lead.kind}</span>
                          <span className="vc-mono" style={{ fontSize: 9 }}>{lead.recommended_service}</span>
                        </div>
                        <div style={{ fontSize: 12, lineHeight: 1.45 }}>{lead.prompt}</div>
                      </div>
                    ))}
                  </div>
                </div>

                {plan.evidence_probes.some((probe) => probe.disconfirming) && (
                  <div
                    style={{
                      borderLeft: "2px solid var(--vc-border-s)",
                      paddingLeft: 10,
                      fontSize: 12,
                      lineHeight: 1.5,
                      color: "var(--vc-muted)",
                    }}
                  >
                    This plan includes disconfirming probes: the system is explicitly
                    looking for evidence that could break the current conclusion.
                  </div>
                )}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

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
  const [gammaState, setGammaState] = useState<"idle" | "generating" | "error">("idle");
  const [gammaError, setGammaError] = useState<string | null>(null);

  const handleGammaPptx = async (e: React.MouseEvent) => {
    e.preventDefault();
    setGammaState("generating");
    setGammaError(null);
    try {
      const url = await generateGammaPptx(sessionId);
      window.open(url, "_blank", "noopener,noreferrer");
      setGammaState("idle");
      setOpen(false);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setGammaError(msg);
      setGammaState("error");
    }
  };

  const formats = [
    { f: "premium-client-package", label: "Клиентский пакет ZIP", strict: true },
    { f: "premium-package", label: "Премиальный черновик ZIP" },
    { f: "premium-docx", label: "Премиальный отчёт DOCX" },
    { f: "premium-pptx", label: "Премиальная презентация PPTX" },
    { f: "docx", label: "Клиентский отчёт DOCX" },
    { f: "pptx", label: "Простая презентация PPTX" },
    { f: "md", label: "Markdown" },
    { f: "json", label: "Данные отчёта JSON" },
    { f: "sources-csv", label: "Источники CSV" },
    { f: "facts-csv", label: "Факты CSV" },
    { f: "data-pack", label: "Полный data pack ZIP" },
    { f: "audit-json", label: "QA-аудит JSON" },
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
                href={exportUrl(sessionId, fmt.f, { allowDraft: !fmt.strict })}
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
            <button
              type="button"
              onClick={handleGammaPptx}
              disabled={gammaState === "generating"}
              style={{
                display: "grid",
                gridTemplateColumns: "56px 1fr",
                gap: 8,
                padding: "8px 10px",
                borderRadius: 8,
                fontSize: 13,
                textAlign: "left",
                background: "transparent",
                border: "none",
                color: "var(--vc-text)",
                cursor: gammaState === "generating" ? "wait" : "pointer",
                width: "100%",
                opacity: gammaState === "generating" ? 0.6 : 1,
              }}
            >
              <span className="vc-mono" style={{ fontSize: 11 }}>
                gamma
              </span>
              <span>
                {gammaState === "generating"
                  ? "Gamma собирает презентацию (1-3 мин)..."
                  : "Gamma PPTX"}
              </span>
            </button>
            {gammaState === "error" && gammaError && (
              <div
                style={{
                  padding: "6px 10px",
                  fontSize: 11,
                  color: "var(--vc-warning, #c44)",
                }}
              >
                Gamma: {gammaError}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
