"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { v3StartResearch } from "@/lib/apiV3";

export default function V3NewPage() {
  const router = useRouter();
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit() {
    const q = question.trim();
    if (!q || busy) return;
    setBusy(true);
    setErr(null);
    try {
      const res = await v3StartResearch(q);
      router.push(`/v3/report/${res.id}`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Не удалось запустить");
      setBusy(false);
    }
  }

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <section className="card" style={{ padding: "2rem" }}>
        <div className="space-y-4">
          <div>
            <h2 className="font-serif text-2xl font-semibold tracking-tight">
              v3 — Матричное исследование
            </h2>
            <p className="text-sm muted mt-1">
              Прямой вход к API v3: planner → scout × N → analyst × N →
              bisociator → summarizer.
            </p>
          </div>

          <textarea
            rows={5}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Сформулируйте исследовательский вопрос…"
            className="resize-none"
            style={{ fontSize: "15px" }}
            disabled={busy}
          />

          {err && <div className="text-sm text-red-600">{err}</div>}

          <div className="flex justify-end pt-2" style={{ borderTop: "1px solid var(--border)" }}>
            <button
              className="btn btn-primary mt-4"
              onClick={submit}
              disabled={!question.trim() || busy}
              style={{ padding: "10px 24px" }}
            >
              {busy ? "Запускаю…" : "Запустить v3"}
            </button>
          </div>
        </div>
      </section>

      <div className="text-xs muted">
        API: <code>{process.env.NEXT_PUBLIC_V3_API_BASE || "http://localhost:8010"}</code>
      </div>
    </div>
  );
}
