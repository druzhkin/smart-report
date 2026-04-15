"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { listReports, type ReportListItem } from "@/lib/api";

export default function LibraryPage() {
  const [items, setItems] = useState<ReportListItem[]>([]);
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listReports().then((r) => {
      setItems(r);
      setLoading(false);
    });
  }, []);

  const filtered = items.filter((i) =>
    i.goal.toLowerCase().includes(q.toLowerCase()) || i.id.includes(q)
  );

  return (
    <div className="space-y-5">
      <div className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Библиотека отчётов</h1>
          <p className="muted text-sm">Сохранено в <code>reports/</code></p>
        </div>
        <input
          className="max-w-sm"
          placeholder="Поиск по цели…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
      </div>

      {loading ? (
        <div className="muted">Загрузка…</div>
      ) : filtered.length === 0 ? (
        <div className="muted">Отчётов пока нет. <Link href="/new" className="underline">Создать первый →</Link></div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {filtered.map((r) => (
            <Link
              href={`/report/${r.id}`}
              key={r.id}
              className="card p-4 hover:shadow-soft transition-shadow group"
            >
              <div className="text-xs muted">{new Date(r.created_at).toLocaleString()}</div>
              <div className="font-medium mt-1 line-clamp-2">{r.goal || r.id}</div>
              <div className="text-xs muted mt-2">
                Блоков: {r.blocks_count} · Связей: {r.connections_count}
              </div>
              {r.top_findings_preview.length > 0 && (
                <ul className="mt-3 space-y-1 text-xs muted opacity-0 group-hover:opacity-100 transition-opacity">
                  {r.top_findings_preview.map((t, i) => (
                    <li key={i} className="truncate">· {t}</li>
                  ))}
                </ul>
              )}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
