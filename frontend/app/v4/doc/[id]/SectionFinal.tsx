"use client";

/**
 * Section 06 — FINAL REPORT
 * 3-column layout: TOC left (sticky) | content center | sidepanel right
 * Inline [N] citations trigger the source sidepanel.
 */

import { useState, useEffect, useRef } from "react";
import { type V4Session } from "@/lib/apiV4";

interface CiteClickFn {
  (n: number): void;
}

interface Props {
  session: V4Session;
  onCiteClick: CiteClickFn;
  onExport: () => void;
}

type TocEntry = { id: string; label: string; depth: number };

function buildToc(report: V4Session["final_report"]): TocEntry[] {
  if (!report) return [];
  const toc: TocEntry[] = [
    { id: "exec",     label: "Резюме",             depth: 1 },
    { id: "qa",       label: "Прямые ответы",       depth: 1 },
    { id: "numbers",  label: "Ключевые цифры",      depth: 1 },
    { id: "ranking",  label: "Ранжирование",         depth: 1 },
    { id: "synthesis",label: "Основной нарратив",   depth: 1 },
    { id: "consensus",label: "Консенсус",            depth: 2 },
    { id: "conflicts",label: "Конфликты",            depth: 2 },
    { id: "gaps",     label: "Закрытые пробелы",    depth: 2 },
    { id: "biblio",   label: "Источники",            depth: 1 },
  ];
  return toc;
}

/** Render text with [N] markers as clickable citation buttons */
function renderWithCites(text: string, onCite: CiteClickFn): React.ReactNode {
  const parts = text.split(/(\[\d+\])/g);
  return parts.map((part, i) => {
    const m = part.match(/^\[(\d+)\]$/);
    if (m) {
      const n = parseInt(m[1], 10);
      return (
        <button key={i} className="vd-cite" onClick={() => onCite(n)}>
          {n}
        </button>
      );
    }
    return <span key={i}>{part}</span>;
  });
}

export function SectionFinal({ session, onCiteClick, onExport }: Props) {
  const report = session.final_report;
  const [activeSection, setActiveSection] = useState("exec");
  const scrollRef = useRef<HTMLDivElement>(null);
  const sectionRefs = useRef<Record<string, HTMLElement | null>>({});

  const toc = buildToc(report);

  function registerRef(id: string) {
    return (el: HTMLElement | null) => { sectionRefs.current[id] = el; };
  }

  function scrollTo(id: string) {
    const el = sectionRefs.current[id];
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  useEffect(() => {
    const root = scrollRef.current;
    if (!root) return;
    const obs = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) {
            setActiveSection(e.target.id.replace("vdr-", ""));
          }
        }
      },
      { root, rootMargin: "-10% 0% -70% 0%", threshold: 0 }
    );
    toc.forEach(({ id }) => {
      const el = sectionRefs.current[id];
      if (el) obs.observe(el);
    });
    return () => obs.disconnect();
  }, [report]);

  if (!report) {
    return (
      <div className="v4-doc" style={{ padding: 40 }}>
        <div style={{ fontFamily: "var(--vd-f-mono)", fontSize: 12, color: "var(--vd-ink-4)" }}>
          Финальный отчёт недоступен
        </div>
      </div>
    );
  }

  const exec = report.executive_summary;
  const sources = report.all_sources ?? [];

  return (
    <div className="vd-report-wrap">
      {/* TOC — left sticky column */}
      <aside className="vd-report-toc">
        <div className="vd-toc-title">Содержание</div>
        {toc.map((t) => (
          <button
            key={t.id}
            className={`vd-toc-item depth-${t.depth}${activeSection === t.id ? " active" : ""}`}
            onClick={() => scrollTo(t.id)}
          >
            {t.label}
          </button>
        ))}

        <div className="vd-toc-title" style={{ marginTop: 20 }}>Сессия</div>
        <div style={{
          fontSize: 11,
          color: "var(--vd-ink-3)",
          padding: "4px 6px 4px 10px",
          fontFamily: "var(--vd-f-mono)",
          lineHeight: 1.8,
          letterSpacing: "0.02em",
        }}>
          {session.source_reports.length} источников
          <br />
          {session.followup_reports.length > 0 && `${session.followup_reports.length} добор`}
          {session.total_cost_rub > 0 && <><br />{Math.round(session.total_cost_rub)}&nbsp;₽</>}
        </div>

        <div style={{ marginTop: 20 }}>
          <button className="vd-copy-btn" onClick={onExport} style={{ width: "100%" }}>
            Экспорт ↓
          </button>
        </div>
      </aside>

      {/* Main content scroll */}
      <div className="vd-report-scroll" ref={scrollRef}>
        <div className="vd-report-inner">

          {/* EXEC — Cover */}
          <section
            id="vdr-exec"
            ref={registerRef("exec")}
            className="vd-report-section"
          >
            <div className="vd-eyebrow">Финальный отчёт · {new Date().toLocaleDateString("ru-RU", { month: "long", year: "numeric" })}</div>
            <h1 className="vd-h1" style={{ fontSize: 28 }}>{report.question}</h1>
            {exec?.main_answer && (
              <p className="vd-lead">{exec.main_answer}</p>
            )}
            {exec?.confidence_note && (
              <div style={{
                fontFamily: "var(--vd-f-mono)",
                fontSize: 11,
                color: "var(--vd-ink-3)",
                marginBottom: 16,
                letterSpacing: "0.04em",
              }}>
                {exec.confidence_note}
              </div>
            )}
            <dl className="vd-cover-meta">
              <div>
                <dt>Источников</dt>
                <dd>{sources.length || session.source_reports.length}</dd>
              </div>
              <div>
                <dt>Стоимость</dt>
                <dd>{Math.round(session.total_cost_rub)}&nbsp;₽</dd>
              </div>
              <div>
                <dt>Добор</dt>
                <dd>{session.followup_reports.length}</dd>
              </div>
              <div>
                <dt>Статус</dt>
                <dd style={{ fontSize: 14 }}>Готов</dd>
              </div>
            </dl>
          </section>

          {/* QA — Direct answers */}
          {exec?.top_findings?.length > 0 && (
            <section
              id="vdr-qa"
              ref={registerRef("qa")}
              className="vd-report-section"
            >
              <h2 className="vd-h2">Ключевые выводы</h2>
              <div style={{ marginTop: 10 }}>
                {exec.top_findings.map((finding, i) => (
                  <div key={i} className="vd-qa-row">
                    <span className="vd-claim-n">F{String(i + 1).padStart(2, "0")}</span>
                    <div className="vd-qa-q" style={{ gridColumn: "2 / 5" }}>{finding}</div>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* KEY NUMBERS */}
          {exec?.key_numbers?.length > 0 && (
            <section
              id="vdr-numbers"
              ref={registerRef("numbers")}
              className="vd-report-section"
            >
              <h2 className="vd-h2">Ключевые цифры</h2>
              <div className="vd-headline-grid" style={{ marginTop: 12 }}>
                {exec.key_numbers.map((kn, i) => (
                  <div key={i} className="vd-headline-cell">
                    <div className="vd-headline-big">{kn.value}</div>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", gap: 8 }}>
                      <div className="vd-headline-lbl">{kn.metric}</div>
                      {kn.source && (
                        <span style={{
                          fontFamily: "var(--vd-f-mono)",
                          fontSize: 10,
                          color: "var(--vd-ink-4)",
                          letterSpacing: "0.04em",
                        }}>
                          {kn.source}
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* RANKING */}
          {exec?.ranking && (
            <section
              id="vdr-ranking"
              ref={registerRef("ranking")}
              className="vd-report-section"
            >
              <h2 className="vd-h2">Ранжирование</h2>
              <p className="vd-p" style={{ color: "var(--vd-ink-3)" }}>{exec.ranking}</p>
            </section>
          )}

          {/* MAIN SYNTHESIS */}
          {report.main_synthesis && (
            <section
              id="vdr-synthesis"
              ref={registerRef("synthesis")}
              className="vd-report-section"
            >
              <h2 className="vd-h2">Основной нарратив</h2>
              <div style={{ fontSize: 14, lineHeight: 1.7, color: "var(--vd-ink)", maxWidth: "64ch" }}>
                {renderWithCites(report.main_synthesis, onCiteClick)}
              </div>
            </section>
          )}

          {/* CONSENSUS */}
          {report.consensus_section && (
            <section
              id="vdr-consensus"
              ref={registerRef("consensus")}
              className="vd-report-section"
            >
              <h2 className="vd-h2">Консенсус источников</h2>
              <div style={{ fontSize: 14, lineHeight: 1.7, color: "var(--vd-ink)", maxWidth: "64ch" }}>
                {renderWithCites(report.consensus_section, onCiteClick)}
              </div>
            </section>
          )}

          {/* CONFLICTS */}
          {report.conflicts_section && (
            <section
              id="vdr-conflicts"
              ref={registerRef("conflicts")}
              className="vd-report-section"
            >
              <h2 className="vd-h2">Ключевые разногласия</h2>
              <div style={{ fontSize: 14, lineHeight: 1.7, color: "var(--vd-ink)", maxWidth: "64ch" }}>
                {renderWithCites(report.conflicts_section, onCiteClick)}
              </div>
            </section>
          )}

          {/* GAPS FILLED */}
          {report.gaps_filled_section && (
            <section
              id="vdr-gaps"
              ref={registerRef("gaps")}
              className="vd-report-section"
            >
              <h2 className="vd-h2">Закрытые пробелы</h2>
              <div style={{ fontSize: 14, lineHeight: 1.7, color: "var(--vd-ink)", maxWidth: "64ch" }}>
                {renderWithCites(report.gaps_filled_section, onCiteClick)}
              </div>
            </section>
          )}

          {/* BIBLIOGRAPHY */}
          {sources.length > 0 && (
            <section
              id="vdr-biblio"
              ref={registerRef("biblio")}
              className="vd-report-section"
            >
              <h2 className="vd-h2">Источники</h2>
              <p className="vd-p" style={{ color: "var(--vd-ink-3)" }}>
                {sources.length} источников использовано в анализе.
              </p>
              <div style={{ marginTop: 12 }}>
                {sources.map((src, i) => (
                  <div key={i} className="vd-biblio-row">
                    <span className="vd-biblio-n">[{i + 1}]</span>
                    <div>
                      <div style={{ fontWeight: 500, fontSize: 12 }}>
                        {src.url ? (
                          <a href={src.url} target="_blank" rel="noopener noreferrer" style={{ color: "var(--vd-ink)", textDecoration: "underline", textDecorationColor: "var(--vd-rule)", textUnderlineOffset: 2 }}>
                            {src.title}
                          </a>
                        ) : (
                          src.title
                        )}
                      </div>
                    </div>
                    <span className="vd-biblio-meta">{src.origin}</span>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Fallback: no sources but has content */}
          {sources.length === 0 && !report.main_synthesis && !exec?.top_findings?.length && (
            <section className="vd-report-section">
              <div style={{ fontFamily: "var(--vd-f-mono)", fontSize: 12, color: "var(--vd-ink-4)" }}>
                Финальный отчёт сформирован. Детальные данные будут доступны после полноценного запуска бэкенда.
              </div>
              <pre style={{ fontSize: 11, color: "var(--vd-ink-3)", fontFamily: "var(--vd-f-mono)", marginTop: 16, whiteSpace: "pre-wrap", maxWidth: "64ch", lineHeight: 1.6 }}>
                {JSON.stringify(report, null, 2).slice(0, 2000)}
              </pre>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}
