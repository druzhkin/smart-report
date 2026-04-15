"use client";

import type { ExecutiveSummary as ES } from "@/lib/api";

export function ExecutiveSummary({ summary }: { summary: ES }) {
  return (
    <section className="prose-editorial">
      <div className="section-eyebrow mb-4">01 · Executive Abstract</div>
      <p className="text-[19px] leading-[1.7]">{summary.goal_restate}</p>

      {summary.top_findings.length > 0 && (
        <>
          <h3>Ключевые находки</h3>
          <ul>
            {summary.top_findings.map((f, i) => (
              <li key={i}>
                <span className="muted text-xs mr-1">[{f.block_cell}]</span>
                {f.headline}
              </li>
            ))}
          </ul>
        </>
      )}

      {summary.top_connections.length > 0 && (
        <>
          <h3>Кросс-доменные связи</h3>
          <ul>
            {summary.top_connections.map((c, i) => (
              <li key={i}>
                <span className="muted text-xs mr-1">{c.domains.join(" ↔ ")}</span>
                {c.headline}
              </li>
            ))}
          </ul>
        </>
      )}

      {summary.key_gaps.length > 0 && (
        <blockquote className="editorial">
          <strong className="not-italic">Пробелы:</strong>{" "}
          {summary.key_gaps.join(" · ")}
        </blockquote>
      )}
    </section>
  );
}
