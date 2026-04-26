"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight, CheckCircle2, AlertTriangle, HelpCircle, Hash } from "lucide-react";
import type { AnalysisOutput } from "@/lib/apiV4";

const CONFIDENCE_STYLE: Record<string, string> = {
  high: "bg-emerald-50 text-emerald-700",
  medium: "bg-amber-50 text-amber-700",
  low: "bg-zinc-100 text-zinc-600",
};

const IMPORTANCE_STYLE: Record<string, string> = {
  critical: "bg-rose-50 text-rose-700",
  material: "bg-amber-50 text-amber-700",
  minor: "bg-zinc-100 text-zinc-600",
};

export function CriticSummary({ analysis }: { analysis: AnalysisOutput }) {
  return (
    <div className="space-y-3">
      {analysis.quality_notes && (
        <div
          className="card text-sm leading-relaxed"
          style={{ padding: "1rem" }}
        >
          <span className="font-medium">Общая оценка: </span>
          <span className="muted">{analysis.quality_notes}</span>
        </div>
      )}

      <Section
        icon={<CheckCircle2 size={14} className="text-emerald-500" />}
        label="Консенсус"
        count={analysis.consensus.length}
        defaultOpen
      >
        <div className="space-y-2">
          {analysis.consensus.map((c, i) => (
            <div key={i} className="text-sm flex items-start gap-3">
              <span
                className={
                  "text-[10px] uppercase font-semibold px-1.5 py-0.5 rounded mt-0.5 flex-shrink-0 " +
                  (CONFIDENCE_STYLE[c.confidence] || "bg-zinc-100")
                }
              >
                {c.confidence}
              </span>
              <div className="flex-1">
                <div>{c.claim}</div>
                <div className="text-[11px] muted mt-0.5">
                  Подтверждают: {c.supporting_sources.join(", ")}
                </div>
              </div>
            </div>
          ))}
          {analysis.consensus.length === 0 && <Empty />}
        </div>
      </Section>

      <Section
        icon={<AlertTriangle size={14} className="text-rose-500" />}
        label="Конфликты"
        count={analysis.conflicts.length}
        defaultOpen={analysis.conflicts.length > 0}
      >
        <div className="space-y-3">
          {analysis.conflicts.map((c, i) => (
            <div
              key={i}
              className="text-sm space-y-2 p-3 rounded-lg"
              style={{
                background: "color-mix(in srgb, var(--border) 20%, var(--bg) 80%)",
              }}
            >
              <div className="flex items-center gap-2">
                <span
                  className={
                    "text-[10px] uppercase font-semibold px-1.5 py-0.5 rounded " +
                    (IMPORTANCE_STYLE[c.importance] || "bg-zinc-100")
                  }
                >
                  {c.importance}
                </span>
                <span className="font-medium">{c.topic}</span>
              </div>
              <div className="grid md:grid-cols-2 gap-3 text-[13px]">
                <div>
                  <div className="text-[11px] uppercase muted font-semibold mb-0.5">
                    {c.source_a}
                  </div>
                  <div>{c.claim_a}</div>
                </div>
                <div>
                  <div className="text-[11px] uppercase muted font-semibold mb-0.5">
                    {c.source_b}
                  </div>
                  <div>{c.claim_b}</div>
                </div>
              </div>
              {c.resolution_hint && (
                <div className="text-[12px] muted border-t pt-2 mt-2" style={{ borderColor: "var(--border)" }}>
                  <span className="font-medium">Разрешение: </span>
                  {c.resolution_hint}
                </div>
              )}
            </div>
          ))}
          {analysis.conflicts.length === 0 && <Empty />}
        </div>
      </Section>

      <Section
        icon={<HelpCircle size={14} className="text-amber-500" />}
        label="Пробелы"
        count={analysis.gaps.length}
        defaultOpen={analysis.gaps.length > 0}
      >
        <div className="space-y-3">
          {analysis.gaps.map((g, i) => (
            <div key={i} className="text-sm space-y-1">
              <div className="font-medium">{g.topic}</div>
              <div className="muted">{g.why_critical}</div>
              <div className="text-[12px]">
                <span className="muted">Что искать: </span>
                {g.what_to_find}
              </div>
              {g.candidate_sources.length > 0 && (
                <div className="flex flex-wrap gap-1 pt-1">
                  {g.candidate_sources.map((s) => (
                    <span
                      key={s}
                      className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-100 text-zinc-600 font-mono"
                    >
                      {s}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))}
          {analysis.gaps.length === 0 && <Empty />}
        </div>
      </Section>

      <Section
        icon={<Hash size={14} className="text-indigo-500" />}
        label="Непроверенные цифры"
        count={analysis.unverified_numbers.length}
      >
        <div className="space-y-2">
          {analysis.unverified_numbers.map((n, i) => (
            <div key={i} className="text-sm flex items-start gap-3">
              <span className="font-mono font-semibold text-indigo-600 whitespace-nowrap">
                {n.value}
              </span>
              <div className="flex-1">
                <div>
                  <span className="font-medium">{n.metric}</span>
                  <span className="muted"> · {n.subject}</span>
                </div>
                <div className="text-[12px] muted">
                  Источник: {n.source_tool} · {n.why_unverified}
                </div>
              </div>
            </div>
          ))}
          {analysis.unverified_numbers.length === 0 && <Empty />}
        </div>
      </Section>
    </div>
  );
}

function Section({
  icon,
  label,
  count,
  defaultOpen,
  children,
}: {
  icon: React.ReactNode;
  label: string;
  count: number;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(!!defaultOpen);
  return (
    <div className="card" style={{ padding: "1rem" }}>
      <button
        className="flex items-center gap-2 w-full text-left"
        onClick={() => setOpen((v) => !v)}
      >
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        {icon}
        <span className="text-sm font-medium">{label}</span>
        <span className="ml-auto text-xs muted">{count}</span>
      </button>
      {open && <div className="mt-3 pl-6">{children}</div>}
    </div>
  );
}

function Empty() {
  return <div className="text-xs muted py-2">Пусто</div>;
}
