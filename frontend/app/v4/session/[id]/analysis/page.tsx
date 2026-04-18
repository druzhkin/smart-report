"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, Sparkles, Upload } from "lucide-react";
import { getSession, synthesize, type V4Session } from "@/lib/apiV4";
import { CriticSummary } from "@/components/v4/CriticSummary";
import { FollowupList } from "@/components/v4/FollowupList";
import { LivePipeline } from "@/components/LivePipeline";

type UIEvent = { event: string; message: string };

export default function V4AnalysisPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = params?.id || "";

  const [session, setSession] = useState<V4Session | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [synthesizing, setSynthesizing] = useState(false);
  const [events, setEvents] = useState<UIEvent[]>([]);

  useEffect(() => {
    if (!id) return;
    getSession(id)
      .then(setSession)
      .catch((e) => setErr(e instanceof Error ? e.message : "Не удалось загрузить"));
  }, [id]);

  async function skipAndSynthesize() {
    if (synthesizing) return;
    setSynthesizing(true);
    setErr(null);
    setEvents([
      { event: "prompt_master", message: "Промт готов" },
      { event: "external_research", message: "Отчёты загружены" },
      { event: "analyzer", message: "Критика готова" },
      { event: "synthesizer", message: "Собираю финальный отчёт (Opus 4.7)" },
    ]);
    try {
      await synthesize(id);
      router.push(`/v4/session/${id}/report`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Не удалось синтезировать");
      setSynthesizing(false);
    }
  }

  if (synthesizing) {
    return (
      <div className="max-w-5xl mx-auto">
        <LivePipeline events={events} goal={session?.raw_question} mode="v4" />
      </div>
    );
  }

  if (err) {
    return (
      <div className="max-w-3xl mx-auto">
        <div className="text-sm text-red-600">{err}</div>
      </div>
    );
  }

  if (!session || !session.analysis) {
    return (
      <div className="max-w-3xl mx-auto">
        <div className="text-sm muted">Загружаю критику…</div>
      </div>
    );
  }

  const a = session.analysis;

  return (
    <div className="max-w-4xl mx-auto space-y-8">
      <header className="space-y-1">
        <div className="text-xs uppercase tracking-widest muted font-medium">
          Шаг 3 из 4 · Критика и добор
        </div>
        {session.raw_question && (
          <h1 className="font-serif text-xl font-semibold tracking-tight headline-gradient">
            {session.raw_question}
          </h1>
        )}
        <p className="text-xs muted pt-1">
          Проанализировано {session.source_reports.length} отчёт(ов).
          Нашли {a.consensus.length} консенсус(ов), {a.conflicts.length} конфликт(ов),{" "}
          {a.gaps.length} пробел(ов), {a.followup_prompts.length} followup-промт(ов).
        </p>
      </header>

      <section className="space-y-3">
        <h2 className="font-serif text-lg font-semibold tracking-tight">
          Анализ отчётов
        </h2>
        <CriticSummary analysis={a} />
      </section>

      <section className="space-y-3">
        <h2 className="font-serif text-lg font-semibold tracking-tight">
          Followup-промты
        </h2>
        <p className="text-sm muted">
          Скопируй и прогони в предложенном инструменте, потом загрузи результат
          на шаге добора. Или пропусти — сразу в синтез.
        </p>
        <FollowupList prompts={a.followup_prompts} />
      </section>

      <div
        className="flex items-center justify-between pt-4 flex-wrap gap-3"
        style={{ borderTop: "1px solid var(--border)" }}
      >
        <Link href={`/v4/session/${id}/upload`} className="btn">
          <ArrowLeft size={14} />
          К загрузке
        </Link>
        <div className="flex items-center gap-3 flex-wrap">
          <button className="btn" onClick={skipAndSynthesize}>
            <Sparkles size={14} />
            Пропустить добор, синтезировать
          </button>
          <button
            className="btn btn-primary"
            onClick={() => router.push(`/v4/session/${id}/dobor`)}
            style={{ padding: "10px 20px" }}
          >
            <Upload size={14} />
            Загрузить добор
          </button>
        </div>
      </div>
    </div>
  );
}
