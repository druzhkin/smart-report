"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { createSession, STUB_ENABLED } from "@/lib/apiV4";
import { ArrowRight, Sparkles } from "lucide-react";

const EXAMPLES = [
  "Что определяет успех девелопера в бизнес-сегменте Москвы — бренд, скорость или продукт?",
  "Как облачные БД изменят enterprise data stack в следующие 3 года?",
  "Что движет оттоком ML-инженеров из бигтеха в стартапы в 2025?",
];

export default function V4NewPage() {
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
      const res = await createSession(q);
      router.push(`/v4/session/${res.session_id}/prompt`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Не удалось создать сессию");
      setBusy(false);
    }
  }

  function onKey(e: React.KeyboardEvent) {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") submit();
  }

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <section className="card relative overflow-hidden" style={{ padding: "2rem" }}>
        <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-violet-400 via-blue-500 to-emerald-400 opacity-50" />

        <div className="flex items-center gap-2 mb-1">
          <Sparkles size={16} className="text-violet-500" />
          <span className="text-xs uppercase tracking-widest muted font-medium">
            v4 · Мета-анализ
          </span>
        </div>

        <h1 className="font-serif text-2xl font-semibold tracking-tight mb-2">
          Новое исследование
        </h1>
        <p className="text-sm muted mb-6 leading-relaxed">
          Сформулируй вопрос — Prompt Master соберёт мощный research-промт,
          который ты скопируешь в Perplexity / OpenAI DR / Claude. Потом
          загрузишь отчёты сюда и получишь синтез трёх голов поверх трёх поисков.
        </p>

        <textarea
          rows={4}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={onKey}
          placeholder="Например: что определяет успех девелопера в бизнес-сегменте Москвы — бренд, скорость или продукт?"
          className="resize-none"
          style={{ fontSize: "15px" }}
          disabled={busy}
        />

        <div className="flex flex-wrap gap-2 mt-3">
          {EXAMPLES.map((s) => (
            <button
              key={s}
              type="button"
              className="btn text-xs"
              onClick={() => setQuestion(s)}
              title={s}
            >
              {s.length > 60 ? s.slice(0, 60) + "…" : s}
            </button>
          ))}
        </div>

        {err && <div className="text-sm text-red-600 mt-4">{err}</div>}

        <div
          className="flex items-center justify-between pt-4 mt-4 flex-wrap gap-3"
          style={{ borderTop: "1px solid var(--border)" }}
        >
          <span className="text-xs muted">
            Cmd/Ctrl + Enter — запустить{STUB_ENABLED ? " · STUB MODE" : ""}
          </span>
          <button
            className="btn btn-primary"
            onClick={submit}
            disabled={!question.trim() || busy}
            style={{ padding: "10px 20px" }}
          >
            <ArrowRight size={14} />
            {busy ? "Создаю…" : "Сгенерировать research-промт"}
          </button>
        </div>
      </section>

      <div className="text-xs muted">
        API: <code>{process.env.NEXT_PUBLIC_V4_API_BASE || process.env.NEXT_PUBLIC_V3_API_BASE || "http://localhost:8010"}</code>
      </div>
    </div>
  );
}
