"use client";

/** Section 04 — CRITIQUE: analysis stats, conflicts/consensus/gaps tabs */

import { useState } from "react";
import { type V4Session } from "@/lib/apiV4";

interface Props {
  session: V4Session;
}

type Tab = "conflicts" | "consensus" | "gaps" | "unverified";

const CONFIDENCE_MAP: Record<string, string> = {
  high: "A",
  medium: "B",
  low: "C",
};

export function SectionCritique({ session }: Props) {
  const analysis = session.analysis;
  const [tab, setTab] = useState<Tab>("conflicts");

  if (!analysis) return null;

  const { consensus, conflicts, gaps, unverified_numbers } = analysis;

  const tabs: Array<[Tab, string, number]> = [
    ["conflicts",   "Противоречия",   conflicts.length],
    ["consensus",   "Согласия",       consensus.length],
    ["gaps",        "Пробелы",        gaps.length],
    ["unverified",  "Неподтв.",       unverified_numbers.length],
  ];

  return (
    <section className="vd-section">
      <div className="vd-section-kicker">
        <span className="vd-kicker-num">04</span>
        Критика и сверка
      </div>
      <h2 className="vd-h2">Анализ источников</h2>

      {/* Stats row */}
      <div className="vd-stats-row">
        {[
          { big: session.source_reports.length, lbl: "Источников" },
          { big: consensus.length,              lbl: "Согласий" },
          { big: conflicts.length,              lbl: "Противоречий" },
          { big: gaps.length,                   lbl: "Пробелов" },
        ].map(({ big, lbl }) => (
          <div key={lbl} className="vd-stat-cell">
            <div className="vd-stat-big">{big}</div>
            <div className="vd-stat-lbl">{lbl}</div>
          </div>
        ))}
      </div>

      {/* Quality notes */}
      {analysis.quality_notes && (
        <p className="vd-p" style={{ color: "var(--vd-ink-3)", marginBottom: 20 }}>
          {analysis.quality_notes}
        </p>
      )}

      {/* Tabs */}
      <div className="vd-conflict-tabs">
        {tabs.map(([key, label, count]) => (
          <button
            key={key}
            className={`vd-ctab${tab === key ? " active" : ""}`}
            onClick={() => setTab(key)}
          >
            {label} <span className="n">{count}</span>
          </button>
        ))}
      </div>

      {/* Tab content */}
      {tab === "conflicts" && (
        <div>
          {conflicts.length === 0 && (
            <div style={{ fontFamily: "var(--vd-f-mono)", fontSize: 12, color: "var(--vd-ink-4)", padding: "16px 0" }}>
              Противоречий не обнаружено
            </div>
          )}
          {conflicts.map((c, i) => (
            <div key={i} className="vd-duel">
              <div className="vd-duel-topic">
                <span className="vd-duel-id">{String(i + 1).padStart(2, "0")}</span>
                <span>{c.topic}</span>
                <span style={{
                  fontFamily: "var(--vd-f-mono)",
                  fontSize: 9,
                  letterSpacing: "0.08em",
                  padding: "2px 6px",
                  textTransform: "uppercase",
                  fontWeight: 600,
                  background: c.importance === "critical" ? "var(--vd-bad)" : c.importance === "material" ? "var(--vd-warn)" : "var(--vd-paper-3)",
                  color: c.importance === "critical" || c.importance === "material" ? "#fff" : "var(--vd-ink-3)",
                }}>
                  {c.importance}
                </span>
              </div>
              <div className="vd-duel-side">
                <div className="vd-duel-side-name">{c.source_a}</div>
                {c.claim_a}
              </div>
              <div className="vd-duel-side">
                <div className="vd-duel-side-name">{c.source_b}</div>
                {c.claim_b}
              </div>
              <div className="vd-duel-res">
                <div className="vd-duel-res-label">Резолюция</div>
                {c.resolution_hint}
              </div>
            </div>
          ))}
        </div>
      )}

      {tab === "consensus" && (
        <div>
          {consensus.length === 0 && (
            <div style={{ fontFamily: "var(--vd-f-mono)", fontSize: 12, color: "var(--vd-ink-4)", padding: "16px 0" }}>
              Консенсус не найден
            </div>
          )}
          {consensus.map((c, i) => (
            <div key={i} className="vd-claim-row">
              <span className="vd-claim-n">A{String(i + 1).padStart(2, "0")}</span>
              <div>
                {c.claim}
                <span style={{ color: "var(--vd-ink-3)", fontFamily: "var(--vd-f-mono)", fontSize: 10, marginLeft: 8 }}>
                  · {c.supporting_sources.length} источн.
                </span>
              </div>
              <span className={`vd-confidence ${(CONFIDENCE_MAP[c.confidence] || "C").toLowerCase()}`}>
                {CONFIDENCE_MAP[c.confidence] ?? "C"}
              </span>
            </div>
          ))}
        </div>
      )}

      {tab === "gaps" && (
        <div>
          {gaps.length === 0 && (
            <div style={{ fontFamily: "var(--vd-f-mono)", fontSize: 12, color: "var(--vd-ink-4)", padding: "16px 0" }}>
              Пробелов не найдено
            </div>
          )}
          {gaps.map((g, i) => (
            <div key={i} className="vd-gap-card">
              <span className="vd-gap-tag critical">Пробел</span>
              <div className="vd-gap-title">{g.topic}</div>
              <div className="vd-gap-meta">
                <strong>Почему важно: </strong>{g.why_critical}
              </div>
              {g.what_to_find && (
                <div className="vd-gap-meta" style={{ marginTop: 6 }}>
                  <strong>Искать: </strong>{g.what_to_find}
                </div>
              )}
              {g.candidate_sources?.length > 0 && (
                <div className="vd-gap-meta" style={{ marginTop: 6 }}>
                  <strong>Источники: </strong>{g.candidate_sources.join(", ")}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {tab === "unverified" && (
        <div>
          {unverified_numbers.length === 0 && (
            <div style={{ fontFamily: "var(--vd-f-mono)", fontSize: 12, color: "var(--vd-ink-4)", padding: "16px 0" }}>
              Неподтверждённых цифр нет
            </div>
          )}
          {unverified_numbers.map((u, i) => (
            <div key={i} className="vd-claim-row">
              <span className="vd-claim-n" style={{ color: "var(--vd-bad)", fontWeight: 600, fontSize: 11 }}>
                {u.value}
              </span>
              <div>
                <div>{u.metric} — {u.subject}</div>
                <div style={{ fontSize: 11, color: "var(--vd-ink-3)", fontFamily: "var(--vd-f-mono)", marginTop: 2 }}>
                  {u.source_tool} · {u.why_unverified}
                </div>
              </div>
              <span className="vd-confidence c">C</span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
