"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, PenSquare, Coins } from "lucide-react";
import { getSession, type V4Session } from "@/lib/apiV4";
import { V4ReportViewer } from "@/components/v4/V4ReportViewer";
import { ExportDropdownV4 } from "@/components/v4/ExportDropdownV4";

export default function V4ReportPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = params?.id || "";

  const [session, setSession] = useState<V4Session | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    getSession(id)
      .then(setSession)
      .catch((e) => setErr(e instanceof Error ? e.message : "Не удалось загрузить"));
  }, [id]);

  if (err) {
    return (
      <div className="max-w-3xl mx-auto">
        <div className="text-sm text-red-600">{err}</div>
      </div>
    );
  }

  if (!session || !session.final_report) {
    return (
      <div className="max-w-3xl mx-auto">
        <div className="text-sm muted">Загружаю финальный отчёт…</div>
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <header className="flex items-start justify-between flex-wrap gap-3">
        <div className="space-y-1">
          <div className="text-xs uppercase tracking-widest muted font-medium">
            Финальный отчёт · v4
          </div>
          <h1 className="font-serif text-2xl font-semibold tracking-tight headline-gradient">
            {session.final_report.question}
          </h1>
        </div>
        <div className="flex items-center gap-3">
          {typeof session.total_cost_rub === "number" && (
            <span className="btn" aria-label="Стоимость">
              <Coins size={14} /> {Math.round(session.total_cost_rub)} ₽
            </span>
          )}
          <ExportDropdownV4 id={id} />
        </div>
      </header>

      <V4ReportViewer report={session.final_report} />

      <div
        className="flex items-center justify-between pt-4"
        style={{ borderTop: "1px solid var(--border)" }}
      >
        <Link href={`/v4/session/${id}/analysis`} className="btn">
          <ArrowLeft size={14} />
          К критике
        </Link>
        <button
          className="btn btn-primary"
          onClick={() => router.push("/v4/new")}
          style={{ padding: "10px 20px" }}
        >
          <PenSquare size={14} />
          Новое исследование
        </button>
      </div>
    </div>
  );
}
