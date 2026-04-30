"use client";

// Smart Report v.IV — artifact content components
// Real API types used for CritiqueArtifact and ReportArtifact.

import { useState, useEffect, useRef } from "react";
import { renderWithCites } from "./primitives";
import type { AnalysisOutput, FinalReport } from "@/lib/apiV4";

// ========== CritiqueArtifact (real AnalysisOutput) ==========
interface CritiqueArtifactProps {
  analysisOutput: AnalysisOutput;
  openSource: (n: number) => void;
}
export function CritiqueArtifact({
  analysisOutput,
  openSource,
}: CritiqueArtifactProps) {
  const [tab, setTab] = useState<
    "conflicts" | "consensus" | "gaps" | "unverified"
  >("conflicts");

  const { consensus, conflicts, gaps, unverified_numbers, followup_prompt } = analysisOutput;

  return (
    <div className="crit-doc">
      <div className="crit-summary">
        <h2>Критика и сверка</h2>
        <div className="lead">
          Найдено {consensus.length} согласий, {conflicts.length} противоречий,{" "}
          {gaps.length} пробелов и {unverified_numbers.length} неподтверждённых
          цифр.
        </div>
        {followup_prompt && (
          <div
            style={{
              marginTop: 12,
              padding: "10px 14px",
              background: "var(--accent-soft)",
              border: "1px solid var(--accent)",
              borderRadius: 4,
              fontSize: 12,
              color: "var(--ink-2)",
              lineHeight: 1.55,
            }}
          >
            <strong>Followup:</strong> {followup_prompt.target_info}
          </div>
        )}
      </div>

      <div className="crit-tabs-row">
        {(
          [
            ["conflicts", "Противоречия", conflicts.length],
            ["consensus", "Согласия", consensus.length],
            ["gaps", "Пробелы", gaps.length],
            ["unverified", "Неподтв. цифры", unverified_numbers.length],
          ] as const
        ).map(([key, label, n]) => (
          <button
            key={key}
            className={"crit-tab-btn" + (tab === key ? " active" : "")}
            onClick={() => setTab(key)}
          >
            {label} <span className="n">{n}</span>
          </button>
        ))}
      </div>

      <div className="crit-content">
        {tab === "conflicts" &&
          (conflicts.length === 0 ? (
            <div style={{ padding: "16px 0", color: "var(--ink-3)" }}>
              Противоречий не найдено
            </div>
          ) : (
            conflicts.map((c, idx) => (
              <div key={idx} className="duel">
                <div className="duel-topic">
                  <span className="duel-id">C{String(idx + 1).padStart(2, "0")}</span>
                  <span>{c.topic}</span>
                  <span
                    style={{
                      marginLeft: "auto",
                      fontSize: 10,
                      fontFamily: "var(--mono)",
                      color:
                        c.importance === "critical"
                          ? "var(--bad)"
                          : c.importance === "material"
                          ? "var(--warn)"
                          : "var(--ink-3)",
                    }}
                  >
                    {c.importance}
                  </span>
                </div>
                <div className="duel-stack">
                  <div className="duel-side">
                    <div className="duel-side-name">{c.source_a}</div>
                    {c.claim_a}
                  </div>
                  <div className="duel-side">
                    <div className="duel-side-name">{c.source_b}</div>
                    {c.claim_b}
                  </div>
                </div>
                {c.resolution_hint && (
                  <div className="duel-res">
                    <div className="duel-res-label">Резолюция</div>
                    {c.resolution_hint}
                  </div>
                )}
              </div>
            ))
          ))}

        {tab === "consensus" &&
          (consensus.length === 0 ? (
            <div style={{ padding: "16px 0", color: "var(--ink-3)" }}>
              Согласий не найдено
            </div>
          ) : (
            consensus.map((a, i) => (
              <div key={i} className="claim-row">
                <span className="claim-n">A{String(i + 1).padStart(2, "0")}</span>
                <div>
                  {a.claim}
                  <span
                    style={{
                      color: "var(--ink-3)",
                      fontFamily: "var(--mono)",
                      fontSize: 10,
                      marginLeft: 8,
                    }}
                  >
                    · {a.supporting_sources.join(", ")}
                  </span>
                </div>
                <span
                  className={
                    "confidence " +
                    (a.confidence === "high"
                      ? "a"
                      : a.confidence === "medium"
                      ? "b"
                      : "c")
                  }
                >
                  {a.confidence === "high" ? "A" : a.confidence === "medium" ? "B" : "C"}
                </span>
              </div>
            ))
          ))}

        {tab === "gaps" &&
          (gaps.length === 0 ? (
            <div style={{ padding: "16px 0", color: "var(--ink-3)" }}>
              Пробелов не найдено
            </div>
          ) : (
            gaps.map((g, i) => (
              <div key={i} className="claim-row">
                <span className="claim-n">G{String(i + 1).padStart(2, "0")}</span>
                <div>
                  <div style={{ fontWeight: 500, fontSize: 13 }}>{g.topic}</div>
                  {g.why_critical && (
                    <div
                      style={{
                        fontSize: 11,
                        color: "var(--ink-3)",
                        fontFamily: "var(--mono)",
                        marginTop: 2,
                      }}
                    >
                      {g.why_critical}
                    </div>
                  )}
                </div>
                <span></span>
              </div>
            ))
          ))}

        {tab === "unverified" &&
          (unverified_numbers.length === 0 ? (
            <div style={{ padding: "16px 0", color: "var(--ink-3)" }}>
              Неподтверждённых цифр не найдено
            </div>
          ) : (
            unverified_numbers.map((u, i) => (
              <div key={i} className="claim-row">
                <span
                  className="claim-n"
                  style={{
                    color: "var(--bad)",
                    fontWeight: 600,
                    fontSize: 11,
                  }}
                >
                  {u.value}
                </span>
                <div>
                  {u.metric} — {u.subject}
                  <div
                    style={{
                      fontSize: 11,
                      color: "var(--ink-3)",
                      fontFamily: "var(--mono)",
                      marginTop: 2,
                    }}
                  >
                    {u.why_unverified}
                  </div>
                </div>
                <span className="confidence c">C</span>
              </div>
            ))
          ))}
      </div>
    </div>
  );
}

// ========== ReportArtifact (real FinalReport from API) ==========
interface ReportArtifactProps {
  finalReport: FinalReport;
  openSource: (n: number) => void;
}
export function ReportArtifact({ finalReport, openSource }: ReportArtifactProps) {
  const { executive_summary, main_synthesis, consensus_section, conflicts_section, gaps_filled_section, all_sources } = finalReport;

  return (
    <div className="report-wrap">
      <aside className="report-toc">
        <div className="title">Разделы</div>
        {[
          ["exec", "Резюме"],
          ["synthesis", "Синтез"],
          ["consensus", "Согласия"],
          ["conflicts", "Противоречия"],
          ["gaps", "Пробелы"],
          ["sources", "Источники"],
        ].map(([id, label]) => (
          <button
            key={id}
            className="toc-item depth-1"
            onClick={() => {
              document.getElementById("r-" + id)?.scrollIntoView({ behavior: "smooth", block: "start" });
            }}
          >
            {label}
          </button>
        ))}
        <div className="title" style={{ marginTop: 18 }}>
          Контекст
        </div>
        <div
          style={{
            fontSize: 11,
            color: "var(--ink-2)",
            padding: "4px 6px 4px 10px",
            fontFamily: "var(--mono)",
            lineHeight: 1.8,
            letterSpacing: "0.02em",
          }}
        >
          {all_sources.length} источников
          {executive_summary.key_numbers?.length ? (
            <>
              <br />
              {executive_summary.key_numbers.length} ключевых цифр
            </>
          ) : null}
        </div>
      </aside>

      <div className="report-scroll">
        <div className="report-inner">
          {/* Резюме */}
          <section id="r-exec" className="cover">
            <div className="eyebrow">Отчёт уровня акционера</div>
            <p
              style={{
                fontSize: 17,
                lineHeight: 1.55,
                fontWeight: 500,
                color: "var(--ink)",
                letterSpacing: "-0.005em",
                margin: "8px 0 16px 0",
              }}
            >
              {renderWithCites(executive_summary.main_answer, openSource)}
            </p>
            {executive_summary.confidence_note && (
              <p style={{ color: "var(--ink-3)", fontSize: 12, fontFamily: "var(--mono)", letterSpacing: "0.02em" }}>
                {renderWithCites(executive_summary.confidence_note, openSource)}
              </p>
            )}
            {executive_summary.top_findings?.length > 0 && (
              <div style={{ marginTop: 16 }}>
                <div
                  style={{
                    fontFamily: "var(--mono)",
                    fontSize: 10,
                    letterSpacing: "0.08em",
                    textTransform: "uppercase",
                    color: "var(--ink-3)",
                    marginBottom: 8,
                  }}
                >
                  Ключевые выводы
                </div>
                <ol style={{ paddingLeft: 20, margin: 0, fontSize: 13, lineHeight: 1.6 }}>
                  {executive_summary.top_findings.map((f, i) => (
                    <li key={i} style={{ marginBottom: 6 }}>{renderWithCites(f, openSource)}</li>
                  ))}
                </ol>
              </div>
            )}
            {executive_summary.key_numbers?.length > 0 && (
              <div className="headline-grid" style={{ marginTop: 20 }}>
                {executive_summary.key_numbers.slice(0, 6).map((kn, i) => (
                  <div key={i} className="headline-cell">
                    <div className="headline-big">{kn.value}</div>
                    <div className="headline-lbl">{kn.metric}</div>
                    {kn.source && (
                      <div
                        style={{
                          fontSize: 10,
                          color: "var(--ink-3)",
                          fontFamily: "var(--mono)",
                          marginTop: 4,
                        }}
                      >
                        {kn.source}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* Main Synthesis */}
          {main_synthesis && (
            <section id="r-synthesis">
              <h2>Основной синтез</h2>
              <div style={{ fontSize: 13, lineHeight: 1.7, color: "var(--ink-2)" }}>
                {main_synthesis.split("\n\n").map((para, i) => (
                  <p key={i}>{renderWithCites(para, openSource)}</p>
                ))}
              </div>
            </section>
          )}

          {/* Consensus */}
          {consensus_section && (
            <section id="r-consensus">
              <h2>Согласия между источниками</h2>
              <div style={{ fontSize: 13, lineHeight: 1.7, color: "var(--ink-2)" }}>
                {consensus_section.split("\n\n").map((para, i) => (
                  <p key={i}>{renderWithCites(para, openSource)}</p>
                ))}
              </div>
            </section>
          )}

          {/* Conflicts */}
          {conflicts_section && (
            <section id="r-conflicts">
              <h2>Ключевые противоречия</h2>
              <div style={{ fontSize: 13, lineHeight: 1.7, color: "var(--ink-2)" }}>
                {conflicts_section.split("\n\n").map((para, i) => (
                  <p key={i}>{renderWithCites(para, openSource)}</p>
                ))}
              </div>
            </section>
          )}

          {/* Gaps */}
          {gaps_filled_section && (
            <section id="r-gaps">
              <h2>Закрытые пробелы</h2>
              <div style={{ fontSize: 13, lineHeight: 1.7, color: "var(--ink-2)" }}>
                {gaps_filled_section.split("\n\n").map((para, i) => (
                  <p key={i}>{renderWithCites(para, openSource)}</p>
                ))}
              </div>
            </section>
          )}

          {/* Sources */}
          {all_sources?.length > 0 && (
            <section id="r-sources">
              <h2>Источники ({all_sources.length})</h2>
              <div style={{ marginTop: 10 }}>
                {all_sources.map((s, i) => (
                  <div key={i} className="biblio-row">
                    <span className="biblio-n">[{i + 1}]</span>
                    <div style={{ fontWeight: 500, fontSize: 12 }}>
                      {s.title || s.url}
                    </div>
                    {s.origin && (
                      <span className="biblio-meta">{s.origin}</span>
                    )}
                  </div>
                ))}
              </div>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}
