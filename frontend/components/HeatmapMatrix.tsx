"use client";

import type { BlockHeader, Matrix } from "@/lib/api";

const prioColor: Record<string, string> = {
  high: "#dc2626",
  medium: "#d97706",
  low: "#16a34a",
};

export function HeatmapMatrix({
  matrix,
  headers,
  onCellClick,
}: {
  matrix: Matrix;
  headers: BlockHeader[];
  onCellClick?: (cell: string) => void;
}) {
  const byCell = new Map(headers.map((h) => [h.cell, h]));
  const maxLayers = Math.max(1, ...matrix.domains.map((d) => d.layers.length));

  return (
    <section>
      <div className="text-xs muted uppercase tracking-wide mb-2">Тепловая карта матрицы</div>
      <div className="card p-3 overflow-x-auto">
        <table className="w-full text-xs border-separate border-spacing-1">
          <thead>
            <tr>
              <th className="text-left muted">Домен \ Слой</th>
              {Array.from({ length: maxLayers }).map((_, i) => (
                <th key={i} className="muted font-normal text-left">Слой {i + 1}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {matrix.domains.map((d) => (
              <tr key={d.name}>
                <td className="pr-2 font-medium">{d.name}</td>
                {Array.from({ length: maxLayers }).map((_, i) => {
                  const layer = d.layers[i];
                  if (!layer) return <td key={i} />;
                  const cell = `${d.name} / ${layer.name}`;
                  const h = byCell.get(cell);
                  const bg = h ? prioColor[h.priority] : undefined;
                  return (
                    <td
                      key={i}
                      onClick={() => onCellClick?.(cell)}
                      className="cursor-pointer rounded"
                      style={{
                        background: bg ? bg + "22" : "transparent",
                        borderLeft: bg ? `3px solid ${bg}` : "3px solid var(--border)",
                        padding: "6px 8px",
                      }}
                      title={cell}
                    >
                      <div className="truncate max-w-[14rem]">{layer.name}</div>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
