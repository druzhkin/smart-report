"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowRight, ArrowLeft } from "lucide-react";
import { getSession, generatePrompt, type ResearchPrompt, type V4Session } from "@/lib/apiV4";
import { PromptCard } from "@/components/v4/PromptCard";
import { LivePipeline } from "@/components/LivePipeline";

export default function V4PromptPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = params?.id || "";

  const [session, setSession] = useState<V4Session | null>(null);
  const [prompt, setPrompt] = useState<ResearchPrompt | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    (async () => {
      try {
        const s = await getSession(id);
        if (cancelled) return;
        setSession(s);
        if (s.research_prompt) {
          setPrompt(s.research_prompt);
        } else {
          setBusy(true);
          try {
            const p = await generatePrompt(id);
            if (!cancelled) setPrompt(p);
          } finally {
            if (!cancelled) setBusy(false);
          }
        }
      } catch (e) {
        if (!cancelled) setErr(e instanceof Error ? e.message : "Не удалось загрузить");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id]);

  async function regenerate() {
    if (busy) return;
    setBusy(true);
    setErr(null);
    try {
      const p = await generatePrompt(id);
      setPrompt(p);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Не удалось перегенерировать");
    } finally {
      setBusy(false);
    }
  }

  if (err) {
    return (
      <div className="max-w-3xl mx-auto">
        <div className="text-sm text-red-600">{err}</div>
      </div>
    );
  }

  if (!prompt) {
    return (
      <div className="max-w-5xl mx-auto">
        <LivePipeline
          events={[{ event: "prompt_master", message: "Генерирую research-промт" }]}
          goal={session?.raw_question}
          mode="v4"
        />
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <header className="space-y-1">
        <div className="text-xs uppercase tracking-widest muted font-medium">
          Шаг 1 из 4 · Research-промт
        </div>
        {session?.raw_question && (
          <h1 className="font-serif text-xl font-semibold tracking-tight headline-gradient">
            {session.raw_question}
          </h1>
        )}
      </header>

      <PromptCard prompt={prompt} onRegenerate={regenerate} busy={busy} />

      <div
        className="flex items-center justify-between pt-4"
        style={{ borderTop: "1px solid var(--border)" }}
      >
        <Link href="/v4/new" className="btn">
          <ArrowLeft size={14} />
          К вопросу
        </Link>
        <button
          className="btn btn-primary"
          onClick={() => router.push(`/v4/session/${id}/upload`)}
          style={{ padding: "10px 20px" }}
        >
          Продолжить
          <ArrowRight size={14} />
        </button>
      </div>
    </div>
  );
}
