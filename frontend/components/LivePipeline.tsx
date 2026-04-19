"use client";

import React, { useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Target,
  Radar,
  Brain,
  GitBranch,
  Sparkles,
  CheckCircle2,
  Circle,
  Loader2,
  AlertTriangle,
  DollarSign,
  Search,
  FileText,
  Link2,
  ExternalLink,
} from "lucide-react";
import type { SSEEvent } from "@/lib/useSSE";

const PHASES = [
  { key: "planner", label: "Декомпозиция цели", icon: Target, pending: false },
  { key: "scout", label: "Разведка источников", icon: Radar, pending: false },
  { key: "analyst", label: "Синтез блоков", icon: Brain, pending: false },
  { key: "bisociator", label: "Поиск связей", icon: GitBranch, pending: false },
  { key: "summarizer", label: "Финальная сборка", icon: Sparkles, pending: false },
] as const;

export const V4_PHASES = [
  { key: "prompt_master", label: "Генерирую research-промт", icon: Target, pending: false },
  { key: "external_research", label: "Ожидаю ваши отчёты", icon: ExternalLink, pending: true },
  { key: "analyzer", label: "Анализирую отчёты", icon: Brain, pending: false },
  { key: "synthesizer", label: "Собираю финал", icon: Sparkles, pending: false },
] as const;

const ICONS: Record<string, any> = {
  planner: Target,
  scout: Radar,
  analyst: Brain,
  bisociator: GitBranch,
  summarizer: Sparkles,
  deepen: Search,
  budget: DollarSign,
  error: AlertTriangle,
  status: Loader2,
  depth: FileText,
  connect: Link2,
  prompt_master: Target,
  external_research: ExternalLink,
  analyzer: Brain,
  synthesizer: Sparkles,
};

const COLORS: Record<string, string> = {
  planner: "text-violet-500",
  scout: "text-blue-500",
  analyst: "text-emerald-500",
  bisociator: "text-amber-500",
  summarizer: "text-indigo-500",
  deepen: "text-fuchsia-500",
  budget: "text-orange-500",
  error: "text-rose-500",
  depth: "text-zinc-500",
  connect: "text-teal-500",
  prompt_master: "text-violet-500",
  external_research: "text-blue-500",
  analyzer: "text-emerald-500",
  synthesizer: "text-indigo-500",
};

function extractDomain(msg: string): string | null {
  const m = msg.match(/https?:\/\/([^\/\s)]+)/);
  return m ? m[1].replace(/^www\./, "") : null;
}

function extractCell(msg: string): string | null {
  const m = msg.match(/\[([A-Za-z0-9_\-\.]+)\]/);
  return m ? m[1] : null;
}

// ---- v4 visual branch (pure-white editorial aesthetic) ----
// Status types used by v4 phase status map
type V4PhaseStatus = "done" | "active" | "waiting" | "pending";

function V4PhaseGlyph({ status }: { status: V4PhaseStatus }) {
  if (status === "done") {
    return (
      <span style={{
        display: "inline-flex", alignItems: "center", justifyContent: "center",
        width: 14, height: 14,
        border: "1px solid var(--v4-accent)",
        background: "var(--v4-accent)",
        color: "var(--v4-paper)",
        flexShrink: 0,
      }}>
        {/* check mark */}
        <svg width="10" height="10" viewBox="0 0 14 14" fill="none">
          <path d="M2 7.5l3.5 3L12 4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="square" strokeLinejoin="miter" />
        </svg>
      </span>
    );
  }
  if (status === "active") {
    return (
      <span style={{
        display: "inline-block",
        width: 12, height: 12,
        border: "1px solid var(--v4-accent)",
        background: "var(--v4-accent)",
        animation: "v4Pulse 1.2s ease-in-out infinite",
        flexShrink: 0,
      }} />
    );
  }
  if (status === "waiting") {
    return (
      <span style={{
        display: "inline-block",
        width: 12, height: 12,
        border: "1px solid var(--v4-accent)",
        background: "var(--v4-accent-wash)",
        flexShrink: 0,
      }} />
    );
  }
  return (
    <span style={{
      display: "inline-block",
      width: 12, height: 12,
      border: "1px solid var(--v4-rule-strong)",
      background: "transparent",
      flexShrink: 0,
    }} />
  );
}

function V4ActiveTicker() {
  const [t, setT] = React.useState(0);
  React.useEffect(() => {
    const id = setInterval(() => setT((v) => v + 1), 700);
    return () => clearInterval(id);
  }, []);
  const dots = ".".repeat((t % 3) + 1);
  return (
    <div style={{
      marginTop: 8, fontFamily: "var(--v4-f-mono)", fontSize: 10,
      color: "var(--v4-ink-2)", letterSpacing: "0.08em", textTransform: "uppercase",
    }}>
      идёт анализ{dots}
    </div>
  );
}

const V4_PHASE_DEFS = [
  { id: "prompt",   label: "Prompt Master",     sub: "формулирует research-промт" },
  { id: "external", label: "External Research", sub: "вы работаете в Perplexity / OpenAI / Claude" },
  { id: "analyzer", label: "Analyzer",          sub: "критикует загруженные отчёты" },
  { id: "synth",    label: "Synthesizer",       sub: "собирает финальный отчёт" },
];

// Map from event keys used in pages to phase ids
function deriveV4Statuses(events: SSEEvent[]): Record<string, V4PhaseStatus> {
  const keyToPhase: Record<string, string> = {
    prompt_master: "prompt",
    external_research: "external",
    analyzer: "analyzer",
    synthesizer: "synth",
  };
  let currentPhaseIdx = -1;
  for (const e of events) {
    const ph = keyToPhase[e.event];
    if (ph) {
      const idx = V4_PHASE_DEFS.findIndex((p) => p.id === ph);
      if (idx > currentPhaseIdx) currentPhaseIdx = idx;
    }
  }
  // Check if we're in a "done" terminal state
  const isDone = events.some((e) => e.event === "done");
  const statuses: Record<string, V4PhaseStatus> = {};
  V4_PHASE_DEFS.forEach((p, i) => {
    if (isDone && i <= currentPhaseIdx) {
      statuses[p.id] = "done";
    } else if (i < currentPhaseIdx) {
      statuses[p.id] = "done";
    } else if (i === currentPhaseIdx) {
      statuses[p.id] = "active";
    } else if (p.id === "external" && currentPhaseIdx === 0) {
      statuses[p.id] = "waiting";
    } else {
      statuses[p.id] = "pending";
    }
  });
  return statuses;
}

function LivePipelineV4({
  events,
  goal,
  compact = false,
  phaseStatus,
}: {
  events: SSEEvent[];
  goal?: string;
  compact?: boolean;
  phaseStatus?: Partial<Record<string, V4PhaseStatus>>;
}) {
  const status = phaseStatus ?? deriveV4Statuses(events);

  return (
    <div style={{
      border: "1px solid var(--v4-rule)",
      background: "var(--v4-paper-2)",
      padding: compact ? 16 : 24,
    }}>
      {!compact && (
        <div style={{ marginBottom: 14, display: "flex", alignItems: "baseline", gap: 12 }}>
          <span style={{ fontFamily: "var(--v4-f-mono)", fontVariantNumeric: "tabular-nums", fontSize: 11, color: "var(--v4-ink-4)" }}>§ 00</span>
          <span style={{ fontFamily: "var(--v4-f-mono)", fontSize: 11, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--v4-ink-3)" }}>Конвейер</span>
        </div>
      )}
      {goal && !compact && (
        <div style={{ marginBottom: 16, fontFamily: "var(--v4-f-display)", fontSize: 18, color: "var(--v4-ink-2)", lineHeight: 1.3 }}>
          {goal}
        </div>
      )}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 0 }}>
        {V4_PHASE_DEFS.map((p, idx) => {
          const s = status[p.id] || "pending";
          const last = idx === V4_PHASE_DEFS.length - 1;
          return (
            <div key={p.id} style={{
              borderLeft: idx === 0 ? "none" : "1px solid var(--v4-rule)",
              paddingLeft: idx === 0 ? 0 : 20,
              paddingRight: last ? 0 : 20,
              position: "relative",
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                <V4PhaseGlyph status={s} />
                <span style={{ fontFamily: "var(--v4-f-mono)", fontSize: 10, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--v4-ink-3)" }}>
                  0{idx + 1}
                </span>
              </div>
              <div style={{
                fontFamily: "var(--v4-f-body)", fontSize: 14, fontWeight: 500,
                color: s === "pending" ? "var(--v4-ink-4)" : "var(--v4-ink)",
                lineHeight: 1.25,
              }}>
                {p.label}
              </div>
              <div style={{
                fontSize: 12, color: s === "pending" ? "var(--v4-ink-4)" : "var(--v4-ink-3)",
                lineHeight: 1.4, marginTop: 4,
              }}>
                {p.sub}
              </div>
              {s === "active" && <V4ActiveTicker />}
              {s === "waiting" && (
                <div style={{
                  marginTop: 8, fontFamily: "var(--v4-f-mono)", fontSize: 10,
                  color: "var(--v4-accent-ink)", letterSpacing: "0.08em", textTransform: "uppercase",
                }}>
                  Ждём вас →
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function LivePipeline({
  events,
  goal,
  mode = "v3",
  phaseStatus,
  compact = false,
}: {
  events: SSEEvent[];
  goal?: string;
  mode?: "v3" | "v4";
  phaseStatus?: Partial<Record<string, V4PhaseStatus>>;
  compact?: boolean;
}) {
  if (mode === "v4") {
    if (compact) {
      return <LivePipelineV4 events={events} goal={goal} phaseStatus={phaseStatus} compact />;
    }
    return (
      <div className="v4" data-theme="v4" style={{ padding: "48px 0" }}>
        <div style={{ maxWidth: 1200, margin: "0 auto", padding: "0 48px" }}>
          <LivePipelineV4 events={events} goal={goal} phaseStatus={phaseStatus} />
        </div>
      </div>
    );
  }

  const phases = PHASES;

  const currentPhase = useMemo(() => {
    for (let i = events.length - 1; i >= 0; i--) {
      const e = events[i].event;
      if (phases.some((p) => p.key === e)) return e;
    }
    return phases[0].key;
  }, [events, phases]);

  const phaseIndex = phases.findIndex((p) => p.key === currentPhase);

  const stats = useMemo(() => {
    let scouts = 0;
    let blocks = 0;
    let connections = 0;
    const domains = new Set<string>();
    for (const e of events) {
      if (e.event === "scout" && /^\[/.test(e.message || "")) scouts++;
      if (e.event === "analyst" && /готов/.test(e.message || "")) blocks++;
      if (e.event === "bisociator" && /Найдено связей:\s*(\d+)/.test(e.message || "")) {
        const m = e.message.match(/Найдено связей:\s*(\d+)/);
        if (m) connections = parseInt(m[1]);
      }
      const d = extractDomain(e.message || "");
      if (d) domains.add(d);
    }
    return { scouts, blocks, connections, domains: domains.size };
  }, [events]);

  const feed = events.slice(-18).reverse();

  return (
    <div className="max-w-5xl mx-auto w-full px-6 md:px-8 py-10 space-y-8">
      <header className="space-y-2">
        <div className="flex items-center gap-3">
          <span className="relative flex h-3 w-3">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-3 w-3 bg-blue-500" />
          </span>
          <span className="text-xs uppercase tracking-widest muted font-medium">
            Исследование идёт
          </span>
        </div>
        {goal && (
          <h1 className="text-2xl md:text-3xl font-serif font-semibold leading-tight headline-gradient">
            {goal}
          </h1>
        )}
      </header>

      {/* Phase tracker */}
      <div className="paper-panel">
        <div
          className="grid gap-2 md:gap-4"
          style={{ gridTemplateColumns: `repeat(${phases.length}, minmax(0, 1fr))` }}
        >
          {phases.map((p, i) => {
            const done = i < phaseIndex;
            const active = i === phaseIndex;
            const pending = !!(p as any).pending && active;
            const Icon = p.icon;
            return (
              <div key={p.key} className="flex flex-col items-center text-center relative">
                {i < phases.length - 1 && (
                  <div
                    className="absolute top-5 left-1/2 w-full h-px -z-0"
                    style={{ background: done ? "#3b82f6" : "#e4e4e7" }}
                  />
                )}
                <div
                  className={
                    "relative z-10 w-10 h-10 rounded-full flex items-center justify-center transition-all " +
                    (pending
                      ? "bg-amber-100 text-amber-600 ring-2 ring-amber-300"
                      : active
                      ? "bg-blue-500 text-white shadow-lg shadow-blue-500/30 scale-110"
                      : done
                      ? "bg-blue-500 text-white"
                      : "bg-zinc-100 text-zinc-400")
                  }
                >
                  {pending ? (
                    <Icon size={16} />
                  ) : active ? (
                    <Loader2 size={16} className="animate-spin" />
                  ) : done ? (
                    <CheckCircle2 size={18} />
                  ) : (
                    <Icon size={16} />
                  )}
                </div>
                <div
                  className={
                    "mt-2 text-[11px] md:text-xs font-medium leading-tight " +
                    (active ? "text-zinc-900" : "text-zinc-500")
                  }
                >
                  {p.label}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Stats — v3 only (v4 returns early above) */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="Scout-задач" value={stats.scouts} icon={Radar} />
        <Stat label="Блоков собрано" value={stats.blocks} icon={Brain} />
        <Stat label="Доменов в поиске" value={stats.domains} icon={Search} />
        <Stat label="Связей" value={stats.connections} icon={Link2} />
      </div>

      {/* Live feed */}
      <div className="paper-panel">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold flex items-center gap-2">
            <Radar size={14} className="text-blue-500" />
            Поток сознания
          </h3>
          <span className="text-xs muted">{events.length} событий</span>
        </div>
        <AnimatePresence initial={false}>
          <div className="space-y-2">
            {feed.length === 0 ? (
              <div className="text-sm muted py-6 text-center">
                Запускаю агентов…
              </div>
            ) : (
              feed.map((e, i) => {
                const Icon = ICONS[e.event] ?? Circle;
                const color = COLORS[e.event] ?? "text-zinc-400";
                const domain = extractDomain(e.message || "");
                const cell = extractCell(e.message || "");
                const msg = (e.message || "").replace(/^\[[^\]]+\]\s*/, "");
                return (
                  <motion.div
                    key={`${e.ts || i}-${e.event}-${i}`}
                    layout
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.2 }}
                    className="flex items-start gap-3 text-sm py-1.5 border-b border-zinc-100 last:border-0"
                  >
                    <Icon size={14} className={`mt-0.5 flex-shrink-0 ${color}`} />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-[10px] uppercase tracking-wider font-semibold muted">
                          {e.event}
                        </span>
                        {cell && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-100 text-zinc-600 font-mono">
                            {cell}
                          </span>
                        )}
                        {domain && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-blue-50 text-blue-700 font-medium">
                            {domain}
                          </span>
                        )}
                      </div>
                      <div className="text-zinc-700 truncate">{msg}</div>
                    </div>
                  </motion.div>
                );
              })
            )}
          </div>
        </AnimatePresence>
      </div>
    </div>
  );
}

function Stat({ label, value, icon: Icon }: { label: string; value: number; icon: any }) {
  return (
    <div className="paper-panel !p-4">
      <div className="flex items-center gap-2 muted text-xs mb-1">
        <Icon size={12} />
        {label}
      </div>
      <motion.div
        key={value}
        initial={{ scale: 1.1 }}
        animate={{ scale: 1 }}
        className="text-2xl font-semibold font-serif"
      >
        {value}
      </motion.div>
    </div>
  );
}
