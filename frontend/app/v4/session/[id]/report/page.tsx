"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { getSession, type V4Session, type FinalReport } from "@/lib/apiV4";
import { useCost } from "@/lib/costContext";
import { SectionKicker } from "@/components/v4/SectionKicker";
import { ToolMark } from "@/components/v4/ToolMark";
import { Icons } from "@/components/v4/Icon";

export default function V4ReportPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = params?.id || "";
  const { setCost } = useCost();

  const [session, setSession] = useState<V4Session | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    getSession(id)
      .then((s) => { setSession(s); setCost(s.total_cost_rub); })
      .catch((e) => setErr(e instanceof Error ? e.message : "Не удалось загрузить"));
  }, [id]);

  if (err) {
    return (
      <div className="v4-container" style={{ paddingTop: 48 }}>
        <div style={{ fontSize: 13, color: "#b91c1c" }}>{err}</div>
      </div>
    );
  }

  if (!session || !session.final_report) {
    return (
      <div className="v4-container" style={{ paddingTop: 48 }}>
        <div style={{ fontSize: 13, color: "var(--v4-ink-3)" }}>Загружаю финальный отчёт…</div>
      </div>
    );
  }

  const r = session.final_report;
  const exec = r.executive_summary;

  return (
    <div style={{ position: "relative", zIndex: 1 }}>
      {/* Document masthead — screen 6 has its own, no chrome bar */}
      <ReportMasthead
        title={r.question}
        generatedAt={String((r.metadata?.generated_at as string) || "")}
        totalCost={session.total_cost_rub}
        onReset={() => router.push("/v4/new")}
        sessionId={id}
      />

      {/* Executive Summary — 2-col */}
      <section className="v4-container-wide" style={{ paddingTop: 56, paddingBottom: 48 }}>
        <SectionKicker number="I">Executive Summary</SectionKicker>

        <div
          style={{
            marginTop: 24,
            display: "grid",
            gridTemplateColumns: "1fr 380px",
            gap: 56,
          }}
        >
          {/* Left: main answer + what meta adds + top findings */}
          <div>
            <p
              className="v4-drop-cap"
              style={{
                fontFamily: "var(--v4-f-display)",
                fontSize: 30,
                lineHeight: 1.3,
                margin: 0,
                color: "var(--v4-ink)",
              }}
            >
              {exec.main_answer}
            </p>

            {exec.what_meta_adds && (
              <div
                style={{
                  marginTop: 32,
                  padding: "18px 22px",
                  borderLeft: "3px solid var(--v4-accent)",
                  background: "var(--v4-accent-wash)",
                }}
              >
                <div
                  className="v4-mono"
                  style={{ color: "var(--v4-accent-ink)", marginBottom: 6 }}
                >
                  Что добавляет мета-анализ
                </div>
                <p
                  style={{
                    fontFamily: "var(--v4-f-display)",
                    fontSize: 17,
                    lineHeight: 1.55,
                    margin: 0,
                    color: "var(--v4-accent-ink)",
                  }}
                >
                  {exec.what_meta_adds}
                </p>
              </div>
            )}

            {/* Top findings */}
            {exec.top_findings.length > 0 && (
              <div style={{ marginTop: 40 }}>
                <SectionKicker>Главные выводы</SectionKicker>
                <ol style={{ marginTop: 16, paddingLeft: 0, listStyle: "none" }}>
                  {exec.top_findings.map((finding, i) => (
                    <li
                      key={i}
                      style={{
                        display: "grid",
                        gridTemplateColumns: "44px 1fr",
                        gap: 16,
                        padding: "14px 0",
                        borderTop: "1px solid var(--v4-rule)",
                        fontSize: 15,
                        lineHeight: 1.55,
                      }}
                    >
                      <span
                        style={{
                          fontFamily: "var(--v4-f-display)",
                          fontSize: 24,
                          lineHeight: 1,
                          color: "var(--v4-ink-3)",
                        }}
                      >
                        {String(i + 1).padStart(2, "0")}
                      </span>
                      <span style={{ color: "var(--v4-ink)" }}>{finding}</span>
                    </li>
                  ))}
                </ol>
              </div>
            )}
          </div>

          {/* Right: ranking + key numbers + confidence */}
          <aside>
            {/* Ranking */}
            {exec.ranking && (
              <>
                <SectionKicker>Ранжирование факторов</SectionKicker>
                <div style={{ marginTop: 14 }}>
                  <div style={{ padding: "14px 0", borderTop: "1px solid var(--v4-rule)" }}>
                    <div
                      style={{
                        display: "flex",
                        alignItems: "baseline",
                        justifyContent: "space-between",
                        marginBottom: 6,
                      }}
                    >
                      <div style={{ fontSize: 13, lineHeight: 1.3 }}>{exec.ranking}</div>
                    </div>
                    <div
                      style={{
                        height: 4,
                        background: "var(--v4-paper-3)",
                        position: "relative",
                      }}
                    >
                      <div
                        style={{
                          position: "absolute",
                          inset: 0,
                          width: "92%",
                          background: "var(--v4-accent)",
                        }}
                      />
                    </div>
                  </div>
                </div>
              </>
            )}

            {/* Key numbers */}
            {exec.key_numbers.length > 0 && (
              <div style={{ marginTop: exec.ranking ? 40 : 0 }}>
                <SectionKicker>Ключевые цифры</SectionKicker>
                <div style={{ marginTop: 14 }}>
                  {exec.key_numbers.map((kn, i) => (
                    <div
                      key={i}
                      style={{
                        display: "grid",
                        gridTemplateColumns: "auto 1fr",
                        gap: 14,
                        padding: "14px 0",
                        borderTop: "1px solid var(--v4-rule)",
                        alignItems: "baseline",
                      }}
                    >
                      <div
                        style={{
                          fontFamily: "var(--v4-f-display)",
                          fontSize: 30,
                          lineHeight: 1,
                          color: "var(--v4-ink)",
                          minWidth: 80,
                        }}
                      >
                        {kn.value}
                      </div>
                      <div>
                        <div style={{ fontSize: 13, lineHeight: 1.4, color: "var(--v4-ink)" }}>
                          {kn.metric}
                        </div>
                        <div
                          className="v4-mono"
                          style={{ fontSize: 9, marginTop: 4, color: "var(--v4-ink-4)" }}
                        >
                          {kn.source}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {exec.confidence_note && (
              <div
                style={{
                  marginTop: 32,
                  fontSize: 12,
                  color: "var(--v4-ink-4)",
                  lineHeight: 1.55,
                  fontStyle: "italic",
                }}
              >
                {exec.confidence_note}
              </div>
            )}
          </aside>
        </div>
      </section>

      {/* Main synthesis — editorial banded section */}
      {r.main_synthesis && (
        <section
          style={{
            background: "var(--v4-paper-2)",
            padding: "64px 0",
            borderTop: "1px solid var(--v4-rule-emphatic)",
            borderBottom: "1px solid var(--v4-rule-emphatic)",
          }}
        >
          <div className="v4-container-wide">
            <SectionKicker number="II">Основной нарратив</SectionKicker>
            <h2
              className="v4-display v4-display-l"
              style={{ marginTop: 18, marginBottom: 36, maxWidth: 900 }}
            >
              Синтез
            </h2>
            <div
              style={{
                columnCount: 3,
                columnGap: 40,
                columnRule: "1px solid var(--v4-rule)",
                fontFamily: "var(--v4-f-display)",
                fontSize: 16,
                lineHeight: 1.65,
                color: "var(--v4-ink-2)",
              }}
            >
              {r.main_synthesis.split("\n\n").filter(Boolean).map((para, i) => (
                <p key={i} style={{ marginTop: i === 0 ? 0 : undefined }}>
                  {para}
                </p>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* Sources */}
      {r.all_sources.length > 0 && (
        <section className="v4-container-wide" style={{ paddingTop: 56, paddingBottom: 96 }}>
          <SectionKicker number="III">Источники</SectionKicker>
          <div
            style={{
              marginTop: 20,
              display: "grid",
              gridTemplateColumns: "repeat(3, 1fr)",
              gap: 0,
              borderTop: "1px solid var(--v4-rule-emphatic)",
            }}
          >
            {/* Group sources by tool */}
            {groupSourcesByTool(r.all_sources).map(({ tool, label, files: sourceFiles }, i) => (
              <div
                key={tool}
                style={{
                  padding: "24px 32px 24px 0",
                  borderLeft: i === 0 ? "none" : "1px solid var(--v4-rule)",
                  paddingLeft: i === 0 ? 0 : 32,
                }}
              >
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    marginBottom: 16,
                  }}
                >
                  <ToolMark tool={tool} size={22} />
                  <span className="v4-mono">{label}</span>
                  <span
                    style={{
                      fontFamily: "var(--v4-f-mono)",
                      fontVariantNumeric: "tabular-nums",
                      fontSize: 11,
                      color: "var(--v4-ink-4)",
                    }}
                  >
                    · {sourceFiles.length}
                  </span>
                </div>
                {sourceFiles.map((f, j) => (
                  <div
                    key={j}
                    style={{
                      display: "grid",
                      gridTemplateColumns: "20px 1fr",
                      gap: 10,
                      alignItems: "baseline",
                      padding: "8px 0",
                      borderTop: "1px solid var(--v4-rule)",
                    }}
                  >
                    <Icons.file style={{ color: "var(--v4-ink-3)", flexShrink: 0 }} />
                    <span
                      style={{
                        fontFamily: "var(--v4-f-mono)",
                        fontSize: 12,
                        color: "var(--v4-ink-2)",
                        wordBreak: "break-all",
                      }}
                    >
                      {f.title || f.url}
                    </span>
                  </div>
                ))}
              </div>
            ))}
          </div>

          <div
            style={{
              marginTop: 64,
              paddingTop: 24,
              borderTop: "1px solid var(--v4-rule-emphatic)",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
            }}
          >
            <span className="v4-mono" style={{ color: "var(--v4-ink-4)" }}>
              — конец отчёта —
            </span>
            <button
              className="v4-btn v4-btn-secondary"
              onClick={() => router.push("/v4/new")}
            >
              Новое исследование <Icons.arrowRight />
            </button>
          </div>
        </section>
      )}
    </div>
  );
}

function ReportMasthead({
  title,
  generatedAt,
  totalCost,
  onReset,
  sessionId,
}: {
  title: string;
  generatedAt: string;
  totalCost: number;
  onReset: () => void;
  sessionId: string;
}) {
  const [exportOpen, setExportOpen] = useState(false);

  return (
    <div
      style={{
        borderBottom: "1px solid var(--v4-rule-emphatic)",
        background: "var(--v4-paper)",
        padding: "24px 0 20px",
      }}
    >
      <div className="v4-container-wide">
        <div
          style={{
            display: "flex",
            alignItems: "baseline",
            justifyContent: "space-between",
            marginBottom: 10,
          }}
        >
          <span
            className="v4-mono"
            style={{ fontSize: 10, letterSpacing: "0.12em" }}
          >
            Мета-аналитический отчёт · Smart Report v.IV
          </span>
          {(generatedAt || totalCost > 0) && (
            <span
              style={{
                fontFamily: "var(--v4-f-mono)",
                fontVariantNumeric: "tabular-nums",
                fontSize: 11,
                color: "var(--v4-ink-3)",
              }}
            >
              {generatedAt && `${generatedAt} · `}
              {totalCost > 0 && `${Math.round(totalCost)} ₽`}
            </span>
          )}
        </div>
        <div
          style={{
            display: "flex",
            alignItems: "flex-end",
            justifyContent: "space-between",
            gap: 32,
          }}
        >
          <h1
            style={{
              fontFamily: "var(--v4-f-display)",
              fontWeight: 400,
              fontSize: "clamp(36px, 5vw, 64px)",
              lineHeight: 1.02,
              margin: 0,
              maxWidth: 900,
              color: "var(--v4-ink)",
              letterSpacing: "-0.01em",
            }}
          >
            {title}
          </h1>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 12,
              flexShrink: 0,
            }}
          >
            <button
              className="v4-btn v4-btn-ghost"
              onClick={onReset}
              style={{ fontSize: 13 }}
            >
              + Новое исследование
            </button>
            <div style={{ position: "relative" }}>
              <button
                className="v4-btn v4-btn-primary"
                onClick={() => setExportOpen(!exportOpen)}
              >
                <Icons.download /> Экспорт
              </button>
              {exportOpen && (
                <ExportDropdown
                  sessionId={sessionId}
                  onClose={() => setExportOpen(false)}
                />
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function ExportDropdown({
  sessionId,
  onClose,
}: {
  sessionId: string;
  onClose: () => void;
}) {
  const formats = [
    { f: ".docx",   label: "Microsoft Word" },
    { f: ".pptx",   label: "PowerPoint" },
    { f: ".md",     label: "Markdown" },
    { f: ".pdf",    label: "PDF (print-ready)" },
    { f: ".gamma",  label: "Gamma App" },
    { f: ".notion", label: "Notion page" },
    { f: ".html",   label: "Standalone HTML" },
  ];

  const baseUrl =
    process.env.NEXT_PUBLIC_V4_API_BASE ||
    process.env.NEXT_PUBLIC_V3_API_BASE ||
    "http://localhost:8010";

  return (
    <>
      <div
        onClick={onClose}
        style={{ position: "fixed", inset: 0, zIndex: 30 }}
      />
      <div
        style={{
          position: "absolute",
          top: "calc(100% + 4px)",
          right: 0,
          background: "var(--v4-paper-2)",
          border: "1px solid var(--v4-rule-emphatic)",
          minWidth: 240,
          zIndex: 40,
          animation: "v4FadeIn .2s ease both",
        }}
      >
        {formats.map((fmt) => (
          <a
            key={fmt.f}
            href={`${baseUrl}/api/v4/sessions/${encodeURIComponent(sessionId)}/export?format=${encodeURIComponent(fmt.f.replace(".", ""))}`}
            target="_blank"
            rel="noreferrer"
            onClick={onClose}
            style={{
              display: "grid",
              gridTemplateColumns: "70px 1fr",
              width: "100%",
              textAlign: "left",
              padding: "10px 14px",
              background: "transparent",
              borderBottom: "1px solid var(--v4-rule)",
              fontFamily: "var(--v4-f-body)",
              fontSize: 13,
              textDecoration: "none",
              color: "var(--v4-ink)",
            }}
          >
            <span
              style={{
                fontFamily: "var(--v4-f-mono)",
                fontVariantNumeric: "tabular-nums",
                fontSize: 11,
                color: "var(--v4-ink-3)",
              }}
            >
              {fmt.f}
            </span>
            <span>{fmt.label}</span>
          </a>
        ))}
      </div>
    </>
  );
}

// Uses the real FinalSource shape from apiV4 — origin is the tool key string
type LocalFinalSource = { title: string; url: string; origin: string };

function groupSourcesByTool(sources: LocalFinalSource[]) {
  const groups: Record<string, { tool: string; label: string; files: LocalFinalSource[] }> = {};
  for (const s of sources) {
    // origin is a free-form string from the backend (e.g. "perplexity", "openai_dr", "claude")
    const t = s.origin || "other";
    if (!groups[t]) {
      const toolMap: Record<string, string> = {
        perplexity: "Perplexity DR",
        openai_dr: "OpenAI DR",
        openai: "OpenAI DR",
        claude: "Claude R",
        other: "Другое",
      };
      groups[t] = { tool: t, label: toolMap[t] || t, files: [] };
    }
    groups[t].files.push(s);
  }
  const entries = Object.values(groups).slice(0, 3);
  // Pad to 3 columns if fewer groups
  while (entries.length < 3) {
    entries.push({ tool: "other", label: "—", files: [] });
  }
  return entries;
}
