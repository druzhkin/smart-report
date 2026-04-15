"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  addDomain,
  connectBlocks,
  deepenCell,
  dismissCell,
  getReport,
  type Report,
} from "@/lib/api";
import { useSSE, type SSEEvent } from "@/lib/useSSE";
import { BlockCard } from "@/components/BlockCard";
import { ExecutiveSummary } from "@/components/ExecutiveSummary";
import { MetricsDashboard } from "@/components/MetricsDashboard";
import { HeatmapMatrix } from "@/components/HeatmapMatrix";
import { ConnectionsGraph } from "@/components/ConnectionsGraph";
import { ConnectionCard } from "@/components/ConnectionCard";
import { AddDomainForm } from "@/components/AddDomainForm";
import { ExportButtons } from "@/components/ExportButtons";

export default function ReportPage() {
  const { id } = useParams<{ id: string }>();
  const [report, setReport] = useState<Report | null>(null);
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());
  const [events, setEvents] = useState<SSEEvent[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [connectMode, setConnectMode] = useState(false);
  const [addDomainOpen, setAddDomainOpen] = useState(false);
  const [domainFilter, setDomainFilter] = useState<string | null>(null);
  const [running, setRunning] = useState(true);

  // SSE stream of progress
  useSSE(id ? `/api/research/${id}/stream` : null, {
    onEvent: (ev) => {
      setEvents((prev) => [...prev.slice(-120), ev]);
      if (ev.event === "done" || ev.event === "close" || ev.event === "error") {
        // refresh report
        getReport(id).then((r) => {
          setReport(r.report);
          setDismissed(new Set(r.dismissed || []));
        });
        if (ev.event !== "error") setRunning(false);
      }
    },
  });

  // initial fetch (in case already completed)
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
  async function onDismiss(cell: string) {
    await dismissCell(id, cell);
    setDismissed((prev) => new Set(prev).add(cell));
  }
  async function onAddDomain(payload: { name?: string; layers?: string[]; freetext?: string }) {
    await addDomain(id, payload);
    setAddDomainOpen(false);
    setRunning(true);
  }
  async function handleBlockClickForConnect(cell: string) {
    if (!connectMode) return;
    setSelected((prev) => {
      if (prev.includes(cell)) return prev.filter((c) => c !== cell);
      const next = [...prev, cell];
      if (next.length === 2) {
        connectBlocks(id, next[0], next[1]).then(() => setRunning(true));
        setConnectMode(false);
        return [];
      }
      return next;
    });
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
      .filter((b) => !domainFilter || b.cell.startsWith(domainFilter))
      .sort((a, b) => {
        const ha = headersByCell.get(a.cell);
        const hb = headersByCell.get(b.cell);
        return (order[ha?.priority] ?? 3) - (order[hb?.priority] ?? 3);
      });
  }, [report, headersByCell, dismissed, domainFilter]);

  const domains = useMemo(
    () => report?.matrix?.domains?.map((d) => d.name) ?? [],
    [report]
  );

  if (!report) {
    return (
      <div className="max-w-2xl mx-auto pt-20 space-y-4">
        <div className="flex items-center gap-3">
          <div className="w-3 h-3 rounded-full bg-brand animate-pulse" />
          <div>Исследование запущено. Получаю матрицу…</div>
        </div>
        <ProgressStream events={events} />
      </div>
    );
  }

  return (
    <div className="relative">
      <div className="fixed top-[-20%] left-[-10%] w-[50%] h-[50%] rounded-full bg-blue-300/10 blur-[120px] pointer-events-none z-0" />
      <div className="fixed bottom-[-20%] right-[-10%] w-[50%] h-[50%] rounded-full bg-indigo-300/10 blur-[120px] pointer-events-none z-0" />
      <div className="relative z-10 grid grid-cols-1 xl:grid-cols-[1fr_420px] gap-6">
      <div className="space-y-6 min-w-0">
        <div className="sticky top-0 z-30 -mx-4 px-4 py-3 backdrop-blur-md bg-[var(--bg)]/70 border-b border-[var(--border)] flex items-center justify-between gap-4 flex-wrap">
          <div className="min-w-0">
            <div className="text-xs muted">Отчёт · {id}{report.budget_exhausted ? " · ⚠️ бюджет исчерпан" : ""}</div>
            <h1 className="text-xl font-semibold font-serif truncate">{report.goal}</h1>
          </div>
          <ExportButtons id={id} />
        </div>
        {report.budget_exhausted && report.budget_note && (
          <div className="card p-3 text-xs border-amber-400/60 bg-amber-50/40 dark:bg-amber-900/10">
            ⚠️ {report.budget_note} — отчёт собран частично.
          </div>
        )}

        {running && <ProgressStream events={events} compact />}

        {report.exec_summary && (
          <ExecutiveSummary summary={report.exec_summary} />
        )}

        <MetricsDashboard blocks={report.blocks} headers={report.block_headers ?? []} />

        <HeatmapMatrix
          matrix={report.matrix}
          headers={report.block_headers ?? []}
          onCellClick={(cell) => {
            const el = document.getElementById(`block-${cell}`);
            el?.scrollIntoView({ behavior: "smooth", block: "center" });
          }}
        />

        <div className="flex items-center gap-2 flex-wrap">
          <button
            className={"btn " + (connectMode ? "btn-primary" : "")}
            onClick={() => {
              setConnectMode((v) => !v);
              setSelected([]);
            }}
          >
            {connectMode ? `Свяжи: выбери ${2 - selected.length}…` : "Свяжи это с тем"}
          </button>
          <button className="btn" onClick={() => setAddDomainOpen(true)}>
            + Добавить домен
          </button>
          <div className="flex gap-1 items-center ml-auto flex-wrap">
            <button
              onClick={() => setDomainFilter(null)}
              className={"btn text-xs " + (!domainFilter ? "btn-primary" : "")}
            >
              Все
            </button>
            {domains.map((d) => (
              <button
                key={d}
                onClick={() => setDomainFilter(d)}
                className={"btn text-xs " + (domainFilter === d ? "btn-primary" : "")}
              >
                {d}
              </button>
            ))}
          </div>
        </div>

        <AnimatePresence>
          {addDomainOpen && (
            <AddDomainForm onSubmit={onAddDomain} onClose={() => setAddDomainOpen(false)} />
          )}
        </AnimatePresence>

        <div className="space-y-3">
          <AnimatePresence initial={false}>
            {sortedBlocks.map((b) => (
              <motion.div
                key={b.cell}
                id={`block-${b.cell}`}
                layout
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.25 }}
              >
                <BlockCard
                  block={b}
                  header={headersByCell.get(b.cell)}
                  selected={selected.includes(b.cell)}
                  connectMode={connectMode}
                  onSelect={handleBlockClickForConnect}
                  onDeepen={onDeepen}
                  onDismiss={onDismiss}
                />
              </motion.div>
            ))}
          </AnimatePresence>
        </div>

        {report.connections?.length > 0 && (
          <section className="space-y-3">
            <h2 className="text-lg font-semibold">Кросс-доменные связи</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {report.connections.map((c, i) => (
                <ConnectionCard key={i} connection={c} />
              ))}
            </div>
          </section>
        )}
      </div>

      <aside className="space-y-4 xl:sticky xl:top-4 self-start">
        <div className="card p-4">
          <h3 className="font-medium mb-2">Граф связей</h3>
          <ConnectionsGraph
            domains={report.matrix.domains.map((d) => d.name)}
            connections={report.connections}
          />
        </div>
        <div className="card p-4">
          <h3 className="font-medium mb-2">Поток событий</h3>
          <ProgressStream events={events} compact />
        </div>
      </aside>
      </div>
    </div>
  );
}

function ProgressStream({ events, compact }: { events: SSEEvent[]; compact?: boolean }) {
  return (
    <div
      className={
        "card p-3 text-xs font-mono overflow-auto " + (compact ? "max-h-48" : "max-h-80")
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
