"use client";

import type { Connection } from "@/lib/api";

const natureColors: Record<string, string> = {
  paradox: "#dc2626",
  causal_chain: "#2563eb",
  unexpected_confirmation: "#16a34a",
  shared_variable: "#7c3aed",
};

export function ConnectionCard({ connection }: { connection: Connection }) {
  const color = natureColors[connection.nature] || "#6b7280";
  return (
    <div
      className="card p-3 text-sm"
      style={{ borderLeft: `4px solid ${color}` }}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="font-medium truncate">{connection.domains.join(" ↔ ")}</div>
        <div className="text-xs muted">{connection.strength}</div>
      </div>
      <div className="text-xs muted mt-1">
        {connection.nature} · {connection.shared_entity}
      </div>
      <div className="mt-2 text-sm leading-snug">{connection.description}</div>
      {connection.novelty && (
        <div className="mt-2 text-xs">
          <span className="muted">Что нового: </span>
          {connection.novelty}
        </div>
      )}
    </div>
  );
}
