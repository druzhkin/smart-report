"use client";

import type { ExecutiveSummary as ES } from "@/lib/api";

export function ExecutiveSummary({ summary }: { summary: ES }) {
  return (
    <section className="card p-5 space-y-4">
      <div>
        <div className="text-xs muted uppercase tracking-wide">Executive Summary</div>
        <div className="font-medium mt-1">{summary.goal_restate}</div>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <div className="text-xs font-semibold mb-1">Топ-5 находок</div>
          <ul className="space-y-1 text-sm">
            {summary.top_findings.map((f, i) => (
              <li key={i}>
                <span className="muted text-xs">[{f.block_cell}]</span> {f.headline}
              </li>
            ))}
          </ul>
        </div>
        <div>
          <div className="text-xs font-semibold mb-1">Топ связей</div>
          <ul className="space-y-1 text-sm">
            {summary.top_connections.map((c, i) => (
              <li key={i}>
                <span className="muted text-xs">
                  {c.domains.join(" ↔ ")}
                </span>{" "}
                {c.headline}
              </li>
            ))}
          </ul>
        </div>
      </div>
      {summary.key_gaps.length > 0 && (
        <div>
          <div className="text-xs font-semibold mb-1">Ключевые пробелы</div>
          <ul className="list-disc ml-5 text-sm muted">
            {summary.key_gaps.map((g, i) => <li key={i}>{g}</li>)}
          </ul>
        </div>
      )}
    </section>
  );
}
