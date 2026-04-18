"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, Upload, Brain, X } from "lucide-react";
import { getSession, uploadReports, analyze, type V4Session } from "@/lib/apiV4";
import { LivePipeline } from "@/components/LivePipeline";

type UIEvent = { event: string; message: string };

export default function V4UploadPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = params?.id || "";

  const [session, setSession] = useState<V4Session | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [events, setEvents] = useState<UIEvent[]>([
    { event: "prompt_master", message: "Research-промт готов" },
    { event: "external_research", message: "Ожидаю загрузки отчётов" },
  ]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    getSession(id).then(setSession).catch(() => {});
  }, [id]);

  function addFiles(list: FileList | File[]) {
    const arr = Array.from(list).filter((f) =>
      /\.(md|txt|markdown)$/i.test(f.name)
    );
    setFiles((prev) => [...prev, ...arr]);
  }

  function remove(i: number) {
    setFiles((prev) => prev.filter((_, j) => j !== i));
  }

  async function run() {
    if (!files.length || analyzing) return;
    setAnalyzing(true);
    setErr(null);
    setEvents((e) => [
      ...e,
      { event: "status", message: `Загружаю ${files.length} отчёт(ов)…` },
    ]);
    try {
      await uploadReports(id, files);
      setEvents((e) => [
        ...e,
        { event: "analyzer", message: "Анализирую отчёты (Opus 4.7)" },
      ]);
      await analyze(id);
      setEvents((e) => [...e, { event: "done", message: "Критика готова" }]);
      router.push(`/v4/session/${id}/analysis`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Не удалось проанализировать");
      setAnalyzing(false);
    }
  }

  if (analyzing) {
    return (
      <div className="max-w-5xl mx-auto">
        <LivePipeline events={events} goal={session?.raw_question} mode="v4" />
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <header className="space-y-1">
        <div className="text-xs uppercase tracking-widest muted font-medium">
          Шаг 2 из 4 · Загрузка отчётов
        </div>
        <h1 className="font-serif text-xl font-semibold tracking-tight">
          Загрузи отчёты из Perplexity / OpenAI DR / Claude
        </h1>
        <p className="text-sm muted">
          Сохрани ответ каждого инструмента как .md или .txt и перетащи сюда.
          Рекомендуется 2–3 отчёта — больше разнообразие источников даёт сильнее
          консенсус и острее конфликты.
        </p>
      </header>

      <section
        className={
          "card border-dashed transition-colors cursor-pointer " +
          (dragOver ? "ring-2 ring-blue-400" : "")
        }
        style={{ padding: "2rem" }}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          if (e.dataTransfer.files) addFiles(e.dataTransfer.files);
        }}
        onClick={() => document.getElementById("v4-upload-input")?.click()}
      >
        <div className="flex flex-col items-center justify-center text-center gap-2">
          <Upload size={20} className="text-blue-500" />
          <div className="text-sm font-medium">
            Перетащи файлы или нажми чтобы выбрать
          </div>
          <div className="text-xs muted">Поддерживаются .md, .txt, .markdown</div>
          <input
            id="v4-upload-input"
            type="file"
            multiple
            accept=".md,.txt,.markdown"
            className="hidden"
            style={{ display: "none" }}
            onChange={(e) => e.target.files && addFiles(e.target.files)}
          />
        </div>
      </section>

      {files.length > 0 && (
        <div className="space-y-2">
          <div className="text-xs uppercase tracking-wider muted font-semibold">
            Загружены ({files.length})
          </div>
          {files.map((f, i) => (
            <div
              key={i}
              className="flex items-center gap-3 px-3 py-2 card text-sm"
            >
              <span className="flex-1 truncate font-mono text-xs">{f.name}</span>
              <span className="text-[11px] muted whitespace-nowrap">
                {Math.round(f.size / 1024)} KB
              </span>
              <button
                className="btn"
                onClick={() => remove(i)}
                aria-label="Удалить"
              >
                <X size={12} />
              </button>
            </div>
          ))}
        </div>
      )}

      {err && <div className="text-sm text-red-600">{err}</div>}

      <div
        className="flex items-center justify-between pt-4"
        style={{ borderTop: "1px solid var(--border)" }}
      >
        <Link href={`/v4/session/${id}/prompt`} className="btn">
          <ArrowLeft size={14} />
          К промту
        </Link>
        <button
          className="btn btn-primary"
          onClick={run}
          disabled={!files.length}
          style={{ padding: "10px 20px" }}
        >
          <Brain size={14} />
          Проанализировать
        </button>
      </div>
    </div>
  );
}
