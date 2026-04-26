"use client";

import { useEffect, useState } from "react";
import { Coins } from "lucide-react";

type Provider = { calls: number; credits: number; estimated?: boolean };
type Cost = {
  total_credits: number;
  currency_label?: string;
  per_provider?: Record<string, Provider>;
  backfilled?: boolean;
};

export function CostBadge({ id }: { id: string }) {
  const [cost, setCost] = useState<Cost | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    fetch(`/api/research/${id}/cost`)
      .then((r) => (r.ok ? r.json() : null))
      .then(setCost)
      .catch(() => {});
  }, [id]);

  if (!cost) return null;
  const cur = cost.currency_label || "₽";
  const total = Math.round(cost.total_credits || 0);

  return (
    <div
      className="relative"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <button className="btn" aria-label="Стоимость отчёта">
        <Coins size={14} /> {total} {cur}
      </button>
      {open && (
        <div className="absolute right-0 mt-2 w-64 card p-3 text-xs shadow-lg z-50 space-y-1.5">
          <div className="font-medium mb-1">Стоимость отчёта</div>
          {cost.per_provider &&
            Object.entries(cost.per_provider).map(([p, v]) => (
              <div key={p} className="flex justify-between">
                <span className="muted">
                  {p}
                  {v.estimated ? " ≈" : ""} · {v.calls}
                </span>
                <span>
                  {Math.round(v.credits)} {cur}
                </span>
              </div>
            ))}
          <div className="flex justify-between border-t pt-1.5 mt-1.5 font-medium">
            <span>Итого</span>
            <span>
              {total} {cur}
            </span>
          </div>
          {cost.backfilled && (
            <div className="muted text-[10px] pt-1">оценка по истории</div>
          )}
        </div>
      )}
    </div>
  );
}
