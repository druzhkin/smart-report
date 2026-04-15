"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { motion, AnimatePresence } from "framer-motion";
import {
  addDomain,
  connectBlocks,
  deepenCell,
  dismissCell,
  getReport,
  type Report,
  type Block,
} from "@/lib/api";
import { useSSE, type SSEEvent } from "@/lib/useSSE";
import { ExecutiveSummary } from "@/components/ExecutiveSummary";
import { MetricsDashboard } from "@/components/MetricsDashboard";
import { HeatmapMatrix } from "@/components/HeatmapMatrix";
import { ConnectionsGraph } from "@/components/ConnectionsGraph";
import { ConnectionCard } from "@/components/ConnectionCard";
import { AddDomainForm } from "@/components/AddDomainForm";
import { ExportButtons } from "@/components/ExportButtons";
import { SourcesSection } from "@/components/SourcesSection";
import { TableOfContents, type TocItem } from "@/components/TableOfContents";
import { ReadingProgress } from "@/components/ReadingProgress";
import { ShareButton } from "@/components/ShareButton";
import { SelectionTooltip } from "@/components/SelectionTooltip";
import { LivePipeline } from "@/components/LivePipeline";
import { CheckCircle2, Clock, BookOpen, ChevronRight } from "lucide-react";

export default function ReportPage() {
  const { id } = useParams<{ id: string }>();
  const [report, setReport] = useState<Report | null>(null);
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());
  const [events, setEvents] = useState<SSEEvent[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [connectMode, setConnectMode] = useState(false);
  const [addDomainOpen, setAddDomainOpen] = useState(false);
  const [running, setRunning] = useState(true);

  useSSE(id ? `/api/research/${id}/stream` : null, {
    onEvent: (ev) => {
      setEvents((prev) => [...prev.slice(-120), ev]);
      if (ev.event === "done" || ev.event === "close" || ev.event === "error") {
        getReport(id).then((r) => {
          setReport(r.report);
          setDismissed(new Set(r.dismissed || []));
        });
        if (ev.event !== "error") setRunning(false);
      }
    },
  });

  useEffect(() => {
    if (!id) return;
    let alive = true;
    const tick = () =>
      getReport(id)
        .then((r) => {
          if (!alive) return;
          setReport(r.report);
          setDismissed(new Set(r.dismissed || []));
          if (r.status === "done") setRunning(false);
        })
        .catch(() => {});
    tick();
    const iv = setInterval(tick, 4000);
    return () => {
      alive = false;
      clearInterval(iv);
    };
  }, [id]);

  async function onDeepen(cell: string, focus: string) {
    await deepenCell(id, cell, focus);
    setRunning(true);
  }
  async function onExpandSelection(text: string, cell: string | null) {
    if (!cell) {
      const first = report?.blocks?.[0]?.cell;
      if (!first) return;
      cell = first;
    }
    await onDeepen(cell, text);
  }
  async function onAddDomain(payload: { name?: string; layers?: string[]; freetext?: string }) {
    await addDomain(id, payload);
    setAddDomainOpen(false);
    setRunning(true);
  }

  const headersByCell = useMemo(() => {
    const m = new Map<string, any>();
    report?.block_headers?.forEach((h) => m.set(h.cell, h));
    return m;
  }, [report]);

  const sortedBlocks = useMemo(() => {
    if (!report) return [];
    const order = { high: 0, medium: 1, low: 2 } as Record<string, number>;
    return [...report.blocks]
      .filter((b) => !dismissed.has(b.cell))
      .sort((a, b) => {
        const ha = headersByCell.get(a.cell);
        const hb = headersByCell.get(b.cell);
        return (order[ha?.priority] ?? 3) - (order[hb?.priority] ?? 3);
      });
  }, [report, headersByCell, dismissed]);

  const sourceIndex = useMemo(() => {
    const m = new Map<string, number>();
    let idx = 1;
    if (!report) return m;
    for (const b of report.blocks) {
      for (const f of b.findings || []) {
        if (f.source && !m.has(f.source)) m.set(f.source, idx++);
      }
    }
    return m;
  }, [report]);

  if (!report) {
    const goalFromId = decodeURIComponent(id || "").replace(/^\d+T\d+-/, "").replace(/-/g, " ");
    return <LivePipeline events={events} goal={goalFromId} />;
  }

  const pullQuote = pickPullQuote(report, headersByCell);

  return (
    <>
      <header className="bg-white/80 backdrop-blur-md border-b border-zinc-200/80 px-8 py-4 flex items-center justify-between sticky top-0 z-40 relative">
        <ReadingProgress />
        <div className="flex items-center gap-2 text-sm text-zinc-500 min-w-0">
          <Link href="/library" className="hover:text-zinc-900 transition-colors">Библиотека</Link>
          <ChevronRight size={14} />
          <span className="text-zinc-900 font-medium truncate max-w-[200px] md:max-w-md">
            {report.goal}
          </span>
        </div>
        <div className="flex items-center gap-3">
          <ExportButtons id={id} />
          <ShareButton />
        </div>
      </header>

      <div className="p-8 max-w-7xl mx-auto w-full">
        <div className="flex flex-col lg:flex-row gap-12 items-start">
          <article
            id="report-article"
            className="flex-1 min-w-0 paper-panel relative"
          >
            <SelectionTooltip containerSelector="#report-article" onExpand={onExpandSelection} />

            <header className="mb-10 border-b border-zinc-100 pb-8">
              <div className="flex flex-wrap items-center gap-3 mb-5">
                <span className="chip chip-success">
                  <CheckCircle2 size={12} />
                  {running ? "In progress" : "Completed"}
                </span>
                <span className="chip">
                  <Clock size={12} />
                  {report.blocks.length} {report.blocks.length === 1 ? "block" : "blocks"}
                </span>
                <span className="chip">
                  <BookOpen size={12} />
                  {sourceIndex.size} sources
                </span>
                <div className="ml-auto flex items-center gap-2 flex-wrap">
                  {report.matrix?.domains?.slice(0, 3).map((d) => (
                    <span
                      key={d.name}
                      className="px-2 py-1 bg-zinc-100/80 text-zinc-600 border border-zinc-200/50 rounded text-xs font-medium max-w-[180px] truncate"
                    >
                      {d.name}
                    </span>
                  ))}
                </div>
              </div>
              <h1 className="text-2xl md:text-3xl font-semibold font-serif leading-[1.2] mb-5 headline-gradient line-clamp-3">
                {report.goal}
              </h1>
              {report.exec_summary?.goal_restate && report.exec_summary.goal_restate !== report.goal && (
                <p className="text-base text-zinc-600 leading-relaxed font-serif line-clamp-4">
                  {report.exec_summary.goal_restate}
                </p>
              )}
            </header>

            {report.budget_exhausted && report.budget_note && (
              <div className="card p-3 text-xs border-amber-400/60 bg-amber-50/40 mb-8">
                ⚠️ {report.budget_note} — отчёт собран частично.
              </div>
            )}

            {running && <ProgressStream events={events} compact />}

            <div className="prose-editorial max-w-none relative space-y-6">
              {report.exec_summary && (
                <section id="sec-exec">
                  <div className="section-eyebrow mb-3">01. Executive Abstract</div>
                  <ul className="space-y-3 list-none pl-0">
                    {report.exec_summary.top_findings.slice(0, 5).map((f, i) => (
                      <li key={i} className="flex gap-3 text-[16px] leading-[1.7]">
                        <span className="flex-shrink-0 w-6 h-6 rounded bg-zinc-100 text-zinc-600 text-xs font-sans font-semibold flex items-center justify-center mt-0.5">
                          {i + 1}
                        </span>
                        <span>
                          <span className="muted text-xs mr-2 font-sans">[{f.block_cell}]</span>
                          {f.headline}
                        </span>
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              {sortedBlocks.map((b, idx) => {
                const header = headersByCell.get(b.cell);
                const num = String(idx + 2).padStart(2, "0");
                return (
                  <section key={b.cell} id={`block-${b.cell}`} data-cell={b.cell} className="scroll-mt-24">
                    <div className="section-eyebrow mb-2 mt-8">
                      {num}. {b.cell}
                    </div>
                    <h2>{header?.one_liner ?? b.cell}</h2>
                    {b.summary && <p className="lead">{renderWithCitations(b.summary, sourceIndex)}</p>}
                    {b.findings.length > 0 && (
                      <ul className="findings">
                        {b.findings.map((f, i) => (
                          <li key={i}>
                            <span className="num">{i + 1}</span>
                            <span>
                              {stripUrls(f.claim)}
                              {f.source && sourceIndex.has(f.source) && (
                                <a
                                  href={f.source}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="cite no-underline"
                                  title={f.source}
                                >
                                  {sourceIndex.get(f.source)}
                                </a>
                              )}
                            </span>
                          </li>
                        ))}
                      </ul>
                    )}
                    {idx === 0 && pullQuote && (
                      <blockquote>
                        «{pullQuote.text}»
                        <cite>— {pullQuote.attribution}</cite>
                      </blockquote>
                    )}
                    {b.gaps.length > 0 && (
                      <p className="text-sm muted italic">
                        Пробелы: {b.gaps.join(" · ")}
                      </p>
                    )}
                    <div className="flex gap-2 mt-2 not-italic font-sans">
                      <button
                        onClick={() => {
                          const q = prompt("Что уточнить в этом блоке?");
                          if (q) onDeepen(b.cell, q);
                        }}
                        className="btn"
                      >
                        Копай глубже
                      </button>
                    </div>
                  </section>
                );
              })}

              {report.connections?.length > 0 && (
                <section id="sec-connections">
                  <div className="section-eyebrow mb-2 mt-10">
                    {String(sortedBlocks.length + 2).padStart(2, "0")}. Кросс-доменные связи
                  </div>
                  <h2>Как домены связаны друг с другом</h2>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3 not-italic font-sans">
                    {report.connections.map((c, i) => (
                      <ConnectionCard key={i} connection={c} />
                    ))}
                  </div>
                </section>
              )}
            </div>

            <div className="mt-16 pt-12 border-t border-zinc-200/80 font-sans">
              <SourcesSection blocks={report.blocks} />
            </div>

            <details className="mt-16 pt-12 border-t border-zinc-200/80 font-sans">
              <summary className="text-sm font-medium cursor-pointer text-zinc-600 hover:text-zinc-900">
                Приложение: метрики, матрица, граф
              </summary>
              <div className="mt-6 space-y-8">
                <MetricsDashboard blocks={report.blocks} headers={report.block_headers ?? []} />
                <HeatmapMatrix
                  matrix={report.matrix}
                  headers={report.block_headers ?? []}
                  onCellClick={(cell) => {
                    document.getElementById(`block-${cell}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
                  }}
                />
                <div className="card p-4">
                  <h3 className="font-medium mb-2 text-sm">Граф связей</h3>
                  <ConnectionsGraph
                    domains={report.matrix.domains.map((d) => d.name)}
                    connections={report.connections}
                  />
                </div>
              </div>
            </details>

            <AnimatePresence>
              {addDomainOpen && (
                <AddDomainForm onSubmit={onAddDomain} onClose={() => setAddDomainOpen(false)} />
              )}
            </AnimatePresence>
          </article>

          <aside className="hidden lg:block w-64 flex-shrink-0 sticky top-24 self-start">
            <TableOfContents items={buildToc(report, sortedBlocks.slice(0, 6))} />
            {running && (
              <div className="card p-4 mt-4">
                <h3 className="font-medium mb-2 text-sm">Поток событий</h3>
                <ProgressStream events={events} compact />
              </div>
            )}
          </aside>
        </div>
      </div>
    </>
  );
}

function stripUrls(text: string): string {
  if (!text) return text;
  return text
    .replace(/\[([^\]]+)\]\((?:https?:\/\/|www\.)[^\s)]+\)/g, "$1")
    .replace(/\((?:https?:\/\/|www\.)[^\s)]+\)/g, "")
    .replace(/<(?:https?:\/\/|www\.)[^\s>]+>/g, "")
    .replace(/(?:https?:\/\/|www\.)\S+/g, "")
    .replace(/\s{2,}/g, " ")
    .replace(/\s+([,.;:!?])/g, "$1")
    .trim();
}

function renderWithCitations(text: string, sourceIndex: Map<string, number>): React.ReactNode[] {
  if (!text) return [];
  const out: React.ReactNode[] = [];
  const mdLink = /\[([^\]]+)\]\(((?:https?:\/\/|www\.)[^\s)]+)\)/g;
  const bareUrl = /(?:https?:\/\/|www\.)\S+/g;
  let lastIdx = 0;
  let key = 0;
  let m: RegExpExecArray | null;
  const pieces: Array<{ start: number; end: number; label: string; url: string }> = [];
  while ((m = mdLink.exec(text))) {
    pieces.push({ start: m.index, end: m.index + m[0].length, label: m[1], url: m[2] });
  }
  pieces.forEach((p) => {
    if (p.start > lastIdx) out.push(text.slice(lastIdx, p.start).replace(bareUrl, ""));
    let idx = sourceIndex.get(p.url);
    if (idx === undefined) {
      sourceIndex.set(p.url, sourceIndex.size + 1);
      idx = sourceIndex.get(p.url);
    }
    out.push(
      <>
        {p.label}
        <a
          key={`c${key++}`}
          href={p.url}
          target="_blank"
          rel="noopener noreferrer"
          className="cite no-underline"
          title={p.url}
        >
          {idx}
        </a>
      </>
    );
    lastIdx = p.end;
  });
  if (lastIdx < text.length) out.push(text.slice(lastIdx).replace(bareUrl, ""));
  return out.map((n, i) => (typeof n === "string" ? <span key={i}>{n}</span> : <span key={i}>{n}</span>));
}

function pickPullQuote(report: Report, headers: Map<string, any>): { text: string; attribution: string } | null {
  let best: { text: string; attribution: string; score: number } | null = null;
  for (const b of report.blocks) {
    const h = headers.get(b.cell);
    const score = (h?.score_novelty ?? 0) + (h?.score_concreteness ?? 0);
    for (const f of b.findings || []) {
      if (!f.claim || f.claim.length < 40 || f.claim.length > 240) continue;
      if (!best || score > best.score) {
        best = {
          text: f.claim,
          attribution: (f as any).source_label || f.source || b.cell,
          score,
        };
      }
    }
  }
  return best;
}

function buildToc(report: Report, blocks: Block[]): TocItem[] {
  const items: TocItem[] = [];
  if (report.exec_summary) items.push({ id: "sec-exec", label: "Executive Abstract" });
  blocks.forEach((b, i) =>
    items.push({
      id: `block-${b.cell}`,
      label: b.cell,
    })
  );
  if (report.connections?.length) items.push({ id: "sec-connections", label: "Связи" });
  items.push({ id: "sec-sources", label: "Источники" });
  return items;
}

function ProgressStream({ events, compact }: { events: SSEEvent[]; compact?: boolean }) {
  return (
    <div
      className={
        "card p-3 text-xs font-mono overflow-auto not-italic font-sans mb-4 " +
        (compact ? "max-h-48" : "max-h-80")
      }
    >
      {events.length === 0 ? (
        <div className="muted">Ожидаю события…</div>
      ) : (
        events.slice(-80).map((e, i) => (
          <div key={i} className="leading-relaxed">
            <span className="muted">[{e.event}]</span>{" "}
            <span className="whitespace-pre-wrap">{e.message}</span>
          </div>
        ))
      )}
    </div>
  );
}
