"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, Sparkles, Upload, X } from "lucide-react";
import { getSession, uploadFollowup, synthesize, type V4Session } from "@/lib/apiV4";
import { LivePipeline } from "@/components/LivePipeline";

type UIEvent = { event: string; message: string };

export default function V4DoborPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = params?.id || "";

  const [session, setSession] = useState<V4Session | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const [busy, setBusy] = useState(false);
  const [events, setEvents] = useState<UIEvent[]>([]);
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
    if (busy) return;
    setBusy(true);
    setErr(null);
    setEvents([
      { event: "prompt_master", message: "Промт готов" },
      { event: "external_research", message: "Отчёты загружены" },
      { event: "analyzer", message: "Критика готова" },
      { event: "status", message: `Загружаю ${files.length} доборных отчёт(ов)…` },
    ]);
    try {
      if (files.length) await uploadFollowup(id, files);
      setEvents((e) => [
        ...e,
        { event: "synthesizer", message: "Собираю финальный отчёт (Opus 4.7)" },
      ]);
      await synthesize(id);
      router.push(`/v4/session/${id}/report`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Не удалось собрать финал");
      setBusy(false);
    }
  }

  if (busy) {
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
          Шаг 4 из 4 · Добор
        </div>
        <h1 className="font-serif text-xl font-semibold tracking-tight">
          Загрузи отчёты по followup-промтам
        </h1>
        <p className="text-sm muted">
          После добора всё пойдёт в синтез. Добор — опциональный шаг, файлы не обязательны.
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
        onClick={() => document.getElementById("v4-dobor-input")?.click()}
      >
        <div className="flex flex-col items-center justify-center text-center gap-2">
          <Upload size={20} className="text-blue-500" />
          <div className="text-sm font-medium">
            Перетащи доборные отчёты или нажми
          </div>
          <div className="text-xs muted">.md, .txt, .markdown</div>
          <input
            id="v4-dobor-input"
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
              <button className="btn" onClick={() => remove(i)}>
                <X size={12} />
              </button>
            </div>
          ))}
        </div>
      )}

      {err && <div className="text-sm text-red-600">{err}</div>}

      <div
        className="flex items-center justify-between pt-4 flex-wrap gap-3"
        style={{ borderTop: "1px solid var(--border)" }}
      >
        <Link href={`/v4/session/${id}/analysis`} className="btn">
          <ArrowLeft size={14} />
          К критике
        </Link>
        <button
          className="btn btn-primary"
          onClick={run}
          style={{ padding: "10px 20px" }}
        >
          <Sparkles size={14} />
          {files.length ? "Синтезировать" : "Синтезировать без добора"}
        </button>
      </div>
    </div>
  );
}
