"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import {
  v3GetReport,
  type V3Report,
  type V3Event,
} from "@/lib/apiV3";
import { useV3Events } from "@/lib/useV3Events";

const PHASE_ORDER = [
  "planner",
  "scout",
  "analyst",
  "bisociator",
  "summarizer",
  "done",
] as const;

const PHASE_LABEL: Record<string, string> = {
  planner: "Planner",
  scout: "Scout",
  analyst: "Analyst",
  bisociator: "Bisociator",
  summarizer: "Summarizer",
  done: "Done",
};

export default function V3ReportPage() {
  const params = useParams<{ id: string }>();
  const jobId = params?.id || null;

  const { events, status, error } = useV3Events(jobId);
  const [report, setReport] = useState<V3Report | null>(null);
  const [reportErr, setReportErr] = useState<string | null>(null);

  useEffect(() => {
    if (!jobId) return;
    if (status !== "done") return;
    (async () => {
      try {
        const res = await v3GetReport(jobId);
        setReport(res.report);
      } catch (e) {
        setReportErr(e instanceof Error ? e.message : "Не удалось загрузить отчёт");
      }
    })();
  }, [jobId, status]);

  const reachedPhases = new Set(events.map((e) => e.phase));
  const activePhase =
    status === "done"
      ? "done"
      : [...events].reverse().find((e) =>
          PHASE_ORDER.includes(e.phase as (typeof PHASE_ORDER)[number])
        )?.phase || "planner";

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <section className="card" style={{ padding: "1.5rem" }}>
        <div className="flex items-center justify-between flex-wrap gap-3">
          <h2 className="font-serif text-xl font-semibold tracking-tight">
            v3 Report · <code className="text-sm">{jobId}</code>
          </h2>
          <span className="text-xs muted">статус: <b>{status}</b></span>
        </div>
        <PhaseTracker
          reached={reachedPhases}
          active={activePhase}
          status={status}
        />
        {(error || reportErr) && (
          <div className="text-sm text-red-600 mt-3">
            {error || reportErr}
          </div>
        )}
      </section>

      <section className="card" style={{ padding: "1.5rem" }}>
        <h3 className="font-serif text-lg font-semibold mb-3">События</h3>
        <EventsFeed events={events} />
      </section>

      {report && <ReportView report={report} />}
    </div>
  );
}

function PhaseTracker({
  reached,
  active,
  status,
}: {
  reached: Set<string>;
  active: string;
  status: string;
}) {
  return (
    <div className="flex gap-2 flex-wrap mt-4">
      {PHASE_ORDER.map((p) => {
        const done = reached.has(p) && p !== active;
        const isActive = p === active && status !== "done";
        const finished = status === "done" && p === "done";
        return (
          <span
            key={p}
            className="px-3 py-1 rounded-full text-xs font-medium"
            style={{
              background: finished
                ? "var(--accent-soft)"
                : isActive
                ? "var(--accent-soft)"
                : done
                ? "color-mix(in srgb, var(--border) 60%, var(--bg) 40%)"
                : "transparent",
              color: isActive || finished ? "var(--accent)" : "var(--fg)",
              border:
                isActive || finished
                  ? "1px solid color-mix(in srgb, var(--accent) 40%, transparent)"
                  : "1px solid var(--border)",
              opacity: done || isActive || finished ? 1 : 0.4,
            }}
          >
            {PHASE_LABEL[p]}
            {isActive && " …"}
          </span>
        );
      })}
    </div>
  );
}

function EventsFeed({ events }: { events: V3Event[] }) {
  if (events.length === 0) {
    return <p className="text-sm muted">Ожидаю события…</p>;
  }
  return (
    <div
      className="space-y-1 text-sm font-mono"
      style={{ maxHeight: "300px", overflowY: "auto" }}
    >
      {events.map((e) => (
        <div
          key={e.seq}
          className="flex gap-3 items-start py-1"
          style={{ borderBottom: "1px solid var(--border)" }}
        >
          <span
            className="text-xs px-1.5 py-0.5 rounded shrink-0"
            style={{
              background: "color-mix(in srgb, var(--border) 40%, transparent)",
              minWidth: "80px",
              textAlign: "center",
            }}
          >
            {e.phase}
          </span>
          <span className="text-xs" style={{ wordBreak: "break-word" }}>
            {e.message}
          </span>
        </div>
      ))}
    </div>
  );
}

function ReportView({ report }: { report: V3Report }) {
  return (
    <>
      <section className="card" style={{ padding: "1.5rem" }}>
        <h3 className="font-serif text-lg font-semibold mb-2">Вопрос</h3>
        <p className="text-base">{report.question.text}</p>
      </section>

      {report.summary && (
        <section className="card" style={{ padding: "1.5rem" }}>
          <h3 className="font-serif text-lg font-semibold mb-3">
            Executive Summary
          </h3>

          <div className="space-y-4">
            <div>
              <div className="text-xs muted mb-1">Main finding</div>
              <p className="text-base leading-relaxed">
                {report.summary.main_finding}
              </p>
            </div>

            {report.summary.top_numbers.length > 0 && (
              <div>
                <div className="text-xs muted mb-2">Top numbers</div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                  {report.summary.top_numbers.map((n, i) => (
                    <div
                      key={i}
                      className="rounded-lg p-3"
                      style={{
                        background: "var(--card)",
                        border: "1px solid var(--border)",
                      }}
                    >
                      <div className="text-lg font-semibold">{n.value}</div>
                      <div className="text-xs muted mt-1">{n.context}</div>
                      {n.source_url && (
                        <a
                          href={n.source_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-xs underline mt-1 inline-block"
                          style={{ color: "var(--accent)" }}
                        >
                          источник
                        </a>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {report.summary.key_tensions.length > 0 && (
              <div>
                <div className="text-xs muted mb-2">Key tensions</div>
                <ul className="space-y-2">
                  {report.summary.key_tensions.map((t, i) => (
                    <li key={i} className="text-sm">
                      <b>{t.tension}</b>
                      <div className="text-xs muted">
                        {t.pole_a} ↔ {t.pole_b}
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {report.summary.open_questions.length > 0 && (
              <div>
                <div className="text-xs muted mb-2">Open questions</div>
                <ul className="space-y-1 text-sm list-disc pl-5">
                  {report.summary.open_questions.map((q, i) => (
                    <li key={i}>{q}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </section>
      )}

      <section className="card" style={{ padding: "1.5rem" }}>
        <h3 className="font-serif text-lg font-semibold mb-3">
          Матрица ({report.matrix.domains.length} доменов ·{" "}
          {report.matrix.cells.length} ячеек)
        </h3>
        <div className="text-sm muted mb-3">
          Домены: {report.matrix.domains.join(" · ")}
        </div>
      </section>

      <section className="card" style={{ padding: "1.5rem" }}>
        <h3 className="font-serif text-lg font-semibold mb-3">
          Блоки ({report.blocks.length})
        </h3>
        <div className="space-y-4">
          {report.blocks.map((b) => (
            <div
              key={b.cell_id}
              className="rounded-lg p-4"
              style={{
                background: "var(--card)",
                border: "1px solid var(--border)",
              }}
            >
              <div className="flex items-center justify-between mb-2">
                <code className="text-xs px-2 py-0.5 rounded" style={{ background: "color-mix(in srgb, var(--border) 40%, transparent)" }}>
                  {b.cell_id}
                </code>
                {b.strongest_number && (
                  <span className="text-sm font-semibold">
                    {b.strongest_number}
                  </span>
                )}
              </div>
              <p className="text-sm mb-2">{b.conclusion}</p>
              {b.gap && (
                <div className="text-xs muted mb-2">
                  <b>Gap:</b> {b.gap}
                </div>
              )}
              {b.findings.length > 0 && (
                <details className="text-xs mt-2">
                  <summary className="cursor-pointer muted">
                    Источников: {b.findings.length}
                  </summary>
                  <ul className="mt-2 space-y-1">
                    {b.findings.map((f, i) => (
                      <li key={i} className="pl-2" style={{ borderLeft: "2px solid var(--border)" }}>
                        <div>{f.claim}</div>
                        {f.source_url && (
                          <a
                            href={f.source_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="underline text-xs"
                            style={{ color: "var(--accent)" }}
                          >
                            {f.source_type} · {new URL(f.source_url).hostname}
                          </a>
                        )}
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </div>
          ))}
        </div>
      </section>

      {report.cross_links.length > 0 && (
        <section className="card" style={{ padding: "1.5rem" }}>
          <h3 className="font-serif text-lg font-semibold mb-3">
            Cross-links ({report.cross_links.length})
          </h3>
          <div className="space-y-3">
            {report.cross_links.map((cl, i) => (
              <div
                key={i}
                className="rounded-lg p-4"
                style={{
                  background: "var(--card)",
                  border: "1px solid var(--border)",
                }}
              >
                <div className="flex gap-2 items-center text-xs mb-2">
                  <code>{cl.cell_a}</code>
                  <span>↔</span>
                  <code>{cl.cell_b}</code>
                  <span
                    className="px-2 py-0.5 rounded text-xs"
                    style={{
                      background: "var(--accent-soft)",
                      color: "var(--accent)",
                    }}
                  >
                    {cl.type}
                  </span>
                </div>
                <div className="text-sm mb-1">
                  <b>Общая переменная:</b> {cl.shared_variable}
                </div>
                <p className="text-sm">{cl.insight}</p>
              </div>
            ))}
          </div>
        </section>
      )}
    </>
  );
}
