"use client";

import type { Connection } from "@/lib/api";
import { AlertTriangle, GitCompare, CheckCircle2, Link2, ArrowRight } from "lucide-react";

const natureMeta: Record<string, { label: string; color: string; bg: string; icon: any }> = {
  paradox: { label: "Парадокс", color: "#b91c1c", bg: "#fef2f2", icon: AlertTriangle },
  causal_chain: { label: "Причинная цепочка", color: "#1d4ed8", bg: "#eff6ff", icon: ArrowRight },
  unexpected_confirmation: { label: "Неожиданное подтверждение", color: "#15803d", bg: "#f0fdf4", icon: CheckCircle2 },
  shared_variable: { label: "Общая переменная", color: "#6d28d9", bg: "#f5f3ff", icon: GitCompare },
};

function strengthLabel(s: any): { text: string; pct: number } {
  const n = typeof s === "number" ? s : parseFloat(s);
  if (!isNaN(n)) {
    const pct = n <= 1 ? Math.round(n * 100) : Math.min(100, Math.round(n));
    const text = pct >= 75 ? "Сильная" : pct >= 45 ? "Средняя" : "Слабая";
    return { text, pct };
  }
  const map: Record<string, number> = { high: 85, medium: 55, low: 30, strong: 85, weak: 30 };
  const key = String(s || "").toLowerCase();
  const pct = map[key] ?? 50;
  return { text: String(s || "—"), pct };
}

export function ConnectionCard({ connection }: { connection: Connection }) {
  const meta = natureMeta[connection.nature] || {
    label: connection.nature || "Связь",
    color: "#52525b",
    bg: "#fafafa",
    icon: Link2,
  };
  const Icon = meta.icon;
  const strength = strengthLabel(connection.strength);

  return (
    <div className="card p-4 text-sm flex flex-col gap-3" style={{ borderTop: `3px solid ${meta.color}` }}>
      <div
        className="inline-flex items-center gap-1.5 self-start text-[11px] font-semibold px-2 py-0.5 rounded"
        style={{ color: meta.color, background: meta.bg }}
      >
        <Icon size={12} />
        {meta.label}
      </div>

      <div className="flex items-center gap-2 text-[13px] font-medium text-zinc-900 flex-wrap">
        <span className="px-2 py-0.5 rounded bg-zinc-100 text-zinc-700">{connection.domains[0]}</span>
        <ArrowRight size={14} className="text-zinc-400 flex-shrink-0" />
        <span className="px-2 py-0.5 rounded bg-zinc-100 text-zinc-700">{connection.domains[1]}</span>
      </div>

      <p className="text-[14px] leading-[1.55] text-zinc-700">{connection.description}</p>

      {connection.shared_entity && (
        <div className="text-xs">
          <span className="muted">Что общего: </span>
          <span className="text-zinc-800 font-medium">{connection.shared_entity}</span>
        </div>
      )}

      {connection.novelty && (
        <div className="text-xs pt-2 border-t border-zinc-100">
          <span className="muted">Почему это ново: </span>
          <span className="text-zinc-700">{connection.novelty}</span>
        </div>
      )}

      <div className="flex items-center gap-2 mt-auto pt-1">
        <span className="text-[11px] muted w-20">{strength.text}</span>
        <div className="flex-1 h-1 bg-zinc-100 rounded overflow-hidden">
          <div className="h-full rounded" style={{ width: `${strength.pct}%`, background: meta.color }} />
        </div>
      </div>
    </div>
  );
}
