"use client";

import type { Block, BlockHeader } from "@/lib/api";
import { useMemo } from "react";

export function MetricsDashboard({
  blocks,
  headers,
}: {
  blocks: Block[];
  headers: BlockHeader[];
}) {
  const items = useMemo(() => {
    const hByCell = new Map(headers.map((h) => [h.cell, h]));
    const withNums: { cell: string; text: string }[] = [];
    for (const h of headers) {
      if (h.strongest_number) withNums.push({ cell: h.cell, text: h.strongest_number });
    }
    if (withNums.length < 6) {
      for (const b of blocks) {
        for (const f of b.findings) {
          if (f.has_numbers && withNums.length < 8) {
            withNums.push({ cell: b.cell, text: f.claim });
          }
        }
      }
    }
    return withNums.slice(0, 8);
  }, [blocks, headers]);

  if (items.length === 0) return null;

  return (
    <section>
      <div className="text-xs muted uppercase tracking-wide mb-2">Ключевые цифры</div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {items.map((m, i) => (
          <div key={i} className="card p-3">
            <div className="text-xs muted truncate">{m.cell}</div>
            <div className="font-medium text-sm mt-1 leading-snug line-clamp-4">
              {m.text}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
