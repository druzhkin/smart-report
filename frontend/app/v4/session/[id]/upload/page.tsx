"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import { getSession, uploadReports, analyze, type V4Session } from "@/lib/apiV4";
import { useCost } from "@/lib/costContext";
import { LivePipeline } from "@/components/LivePipeline";
import { ProcessingOverlay } from "@/components/v4/ProcessingOverlay";
import { SectionKicker } from "@/components/v4/SectionKicker";
import { ToolMark, TOOL_DEFS } from "@/components/v4/ToolMark";
import { Icons } from "@/components/v4/Icon";

type UIFile = {
  id: string;
  file: File;
  name: string;
  tool: string;
  words: number;
};

type UIEvent = { event: string; message: string };

function detectTool(filename: string): string {
  const lower = filename.toLowerCase();
  if (lower.includes("perplex")) return "perplexity";
  if (lower.includes("openai") || lower.includes("chatgpt") || lower.includes("gpt")) return "openai";
  if (lower.includes("claude")) return "claude";
  return "other";
}

function pluralRu(n: number, forms: [string, string, string]): string {
  const m10 = n % 10, m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return forms[0];
  if (m10 >= 2 && m10 <= 4 && (m100 < 10 || m100 >= 20)) return forms[1];
  return forms[2];
}

export default function V4UploadPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = params?.id || "";
  const { setCost } = useCost();

  const [session, setSession] = useState<V4Session | null>(null);
  const [files, setFiles] = useState<UIFile[]>([]);
  const [dragging, setDragging] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [events, setEvents] = useState<UIEvent[]>([
    { event: "prompt_master", message: "Research-промт готов" },
    { event: "external_research", message: "Ожидаю загрузки отчётов" },
  ]);
  const [err, setErr] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!id) return;
    getSession(id).then((s) => { setSession(s); setCost(s.total_cost_rub); }).catch(() => {});
  }, [id]);

  const addFiles = useCallback((rawList: File[]) => {
    const allowed = [".md", ".markdown", ".txt"];
    const next: UIFile[] = [];
    for (const f of rawList) {
      const ok = allowed.some((ext) => f.name.toLowerCase().endsWith(ext));
      if (!ok) continue;
      next.push({
        id: Math.random().toString(36).slice(2),
        file: f,
        name: f.name,
        tool: detectTool(f.name),
        words: Math.round(f.size / 6),
      });
    }
    setFiles((prev) => [...prev, ...next]);
  }, []);

  async function run() {
    if (!files.length || analyzing) return;
    setAnalyzing(true);
    setErr(null);
    setEvents((e) => [
      ...e,
      { event: "status", message: `Загружаю ${files.length} отчёт(ов)…` },
    ]);
    try {
      await uploadReports(id, files.map((f) => f.file));
      setEvents((e) => [...e, { event: "analyzer", message: "Анализирую отчёты" }]);
      await analyze(id);
      router.push(`/v4/session/${id}/analysis`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Не удалось проанализировать");
      setAnalyzing(false);
    }
  }

  if (analyzing) {
    return <ProcessingOverlay stage="analyzer" />;
  }

  const fileCount = files.length;

  return (
    <div
      className="v4-container"
      style={{ paddingTop: 48, paddingBottom: 96, position: "relative", zIndex: 1 }}
    >
      {/* Breadcrumb */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 32 }}>
        <span className="v4-mono" style={{ color: "var(--v4-ink-4)" }}>Промт / </span>
        <span className="v4-mono">Загрузка отчётов</span>
        <span style={{ width: 16, height: 1, background: "var(--v4-rule-strong)" }} />
        <span className="v4-mono" style={{ color: "var(--v4-ink-4)" }}>Критика →</span>
      </div>

      <SectionKicker number="03">Загрузка отчётов</SectionKicker>
      <h1
        className="v4-display v4-display-l"
        style={{ marginTop: 18, marginBottom: 16, maxWidth: 760 }}
      >
        Загрузите отчёты, которые вы получили из&nbsp;поисковиков.
      </h1>
      <p style={{ fontSize: 15, color: "var(--v4-ink-3)", maxWidth: 640, marginBottom: 40 }}>
        От&nbsp;одного до&nbsp;пяти файлов. Чем больше источников, тем больше противоречий
        найдёт Analyzer — а&nbsp;противоречия это&nbsp;и&nbsp;есть то, ради чего всё&nbsp;делается.
      </p>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1.5fr 1fr",
          gap: 48,
          alignItems: "start",
        }}
      >
        {/* Upload zone */}
        <div>
          <UploadZone
            files={files}
            setFiles={setFiles}
            dragging={dragging}
            setDragging={setDragging}
            addFiles={addFiles}
            inputRef={inputRef}
          />

          <div
            style={{
              marginTop: 32,
              paddingTop: 20,
              borderTop: "1px solid var(--v4-rule)",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
            }}
          >
            <div style={{ fontSize: 13, color: "var(--v4-ink-3)" }}>
              {fileCount === 0
                ? "Добавьте хотя бы один файл"
                : `${fileCount} ${pluralRu(fileCount, ["файл", "файла", "файлов"])} готово к анализу`}
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <button
                className="v4-btn v4-btn-secondary"
                onClick={() => router.push(`/v4/session/${id}/prompt`)}
              >
                <Icons.arrowLeft /> Назад к промту
              </button>
              <button
                className="v4-btn v4-btn-primary"
                onClick={run}
                disabled={fileCount === 0}
              >
                Проанализировать <Icons.arrowRight />
              </button>
            </div>
          </div>

          {err && (
            <div style={{ marginTop: 12, fontSize: 13, color: "#b91c1c" }}>{err}</div>
          )}
        </div>

        {/* Aside */}
        <aside style={{ borderLeft: "1px solid var(--v4-rule)", paddingLeft: 32 }}>
          <LivePipeline
            events={[]}
            goal={undefined}
            mode="v4"
            compact
            phaseStatus={{
              prompt: "done",
              external: fileCount > 0 ? "done" : "waiting",
              analyzer: "pending",
              synth: "pending",
            }}
          />

          <div style={{ marginTop: 24 }}>
            <SectionKicker>Примечание</SectionKicker>
            <p style={{ fontSize: 13, color: "var(--v4-ink-3)", lineHeight: 1.6, marginTop: 10 }}>
              Инструмент определяется автоматически по имени файла (например,{" "}
              <span style={{ fontFamily: "var(--v4-f-mono)", fontVariantNumeric: "tabular-nums" }}>
                perplexity-2026-04-18.md
              </span>
              ). Если ошибся — поправьте вручную.
            </p>
          </div>
        </aside>
      </div>
    </div>
  );
}

function UploadZone({
  files,
  setFiles,
  dragging,
  setDragging,
  addFiles,
  inputRef,
}: {
  files: UIFile[];
  setFiles: (f: UIFile[]) => void;
  dragging: boolean;
  setDragging: (v: boolean) => void;
  addFiles: (list: File[]) => void;
  inputRef: React.RefObject<HTMLInputElement>;
}) {
  return (
    <div>
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          addFiles(Array.from(e.dataTransfer.files || []));
        }}
        onClick={() => inputRef.current?.click()}
        style={{
          border: `1px ${dragging ? "solid" : "dashed"} ${dragging ? "var(--v4-accent)" : "var(--v4-rule-strong)"}`,
          background: dragging ? "var(--v4-accent-wash)" : "var(--v4-paper-2)",
          padding: "56px 32px",
          textAlign: "center",
          cursor: "pointer",
          transition: "all .15s ease",
        }}
      >
        <div
          style={{
            display: "inline-flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 10,
          }}
        >
          <Icons.upload style={{ color: "var(--v4-ink-3)" }} />
          <div
            style={{
              fontFamily: "var(--v4-f-display)",
              fontSize: 24,
              fontWeight: 400,
              letterSpacing: "-0.01em",
              color: "var(--v4-ink)",
              marginTop: 6,
            }}
          >
            Перетащите сюда отчёты
          </div>
          <div style={{ color: "var(--v4-ink-3)", fontSize: 13 }}>
            или{" "}
            <span style={{ textDecoration: "underline" }}>выберите файлы</span>{" "}
            вручную
          </div>
          <div className="v4-mono" style={{ marginTop: 4 }}>
            .md · .markdown · .txt · до 5 файлов
          </div>
        </div>
        <input
          ref={inputRef}
          type="file"
          accept=".md,.markdown,.txt"
          multiple
          hidden
          onChange={(e) => addFiles(Array.from(e.target.files || []))}
        />
      </div>

      {files.length > 0 && (
        <div style={{ marginTop: 24, display: "flex", flexDirection: "column", gap: 0 }}>
          <div
            style={{
              display: "flex",
              alignItems: "baseline",
              justifyContent: "space-between",
              marginBottom: 10,
            }}
          >
            <span className="v4-mono">Загружено · {files.length}</span>
            <button
              onClick={() => setFiles([])}
              style={{
                background: "transparent",
                border: "none",
                cursor: "pointer",
                fontFamily: "var(--v4-f-mono)",
                fontSize: 10,
                letterSpacing: "0.08em",
                textTransform: "uppercase",
                color: "var(--v4-ink-3)",
              }}
            >
              Очистить
            </button>
          </div>
          {files.map((f, i) => (
            <FileCard
              key={f.id}
              file={f}
              onChange={(patch) => {
                const next = [...files];
                next[i] = { ...next[i], ...patch };
                setFiles(next);
              }}
              onRemove={() => setFiles(files.filter((x) => x.id !== f.id))}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function FileCard({
  file,
  onChange,
  onRemove,
}: {
  file: UIFile;
  onChange: (patch: Partial<UIFile>) => void;
  onRemove: () => void;
}) {
  const [editingTool, setEditingTool] = useState(false);
  const def = TOOL_DEFS[file.tool] || TOOL_DEFS.other;

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "auto 1fr auto auto auto",
        gap: 20,
        alignItems: "center",
        padding: "16px 0",
        borderTop: "1px solid var(--v4-rule)",
      }}
    >
      <ToolMark tool={file.tool} size={28} />

      <div>
        <div
          style={{
            fontWeight: 500,
            fontSize: 14,
            fontFamily: "var(--v4-f-body)",
            color: "var(--v4-ink)",
          }}
        >
          {file.name}
        </div>
        <div style={{ fontSize: 12, color: "var(--v4-ink-3)", marginTop: 2 }}>
          ~{new Intl.NumberFormat("ru-RU").format(file.words)} слов
        </div>
      </div>

      <div style={{ position: "relative" }}>
        <button
          onClick={() => setEditingTool(!editingTool)}
          style={{
            background: "transparent",
            border: "1px solid var(--v4-rule)",
            padding: "4px 8px",
            fontSize: 11,
            cursor: "pointer",
            fontFamily: "var(--v4-f-mono)",
            letterSpacing: "0.06em",
            color: "var(--v4-ink-2)",
          }}
        >
          {def.label} ▾
        </button>
        {editingTool && (
          <div
            style={{
              position: "absolute",
              top: "calc(100% + 4px)",
              right: 0,
              background: "var(--v4-paper-2)",
              border: "1px solid var(--v4-rule-emphatic)",
              zIndex: 20,
              minWidth: 160,
            }}
          >
            {Object.keys(TOOL_DEFS).map((k) => (
              <button
                key={k}
                onClick={() => { onChange({ tool: k }); setEditingTool(false); }}
                style={{
                  display: "block",
                  width: "100%",
                  textAlign: "left",
                  padding: "8px 12px",
                  background: k === file.tool ? "var(--v4-paper-3)" : "transparent",
                  color: "var(--v4-ink-2)",
                  border: "none",
                  cursor: "pointer",
                  fontFamily: "var(--v4-f-body)",
                  fontSize: 13,
                }}
              >
                {TOOL_DEFS[k].label}
              </button>
            ))}
          </div>
        )}
      </div>

      <span
        style={{
          fontFamily: "var(--v4-f-mono)",
          fontVariantNumeric: "tabular-nums",
          fontSize: 12,
          color: "var(--v4-ink-3)",
        }}
      >
        ~{new Intl.NumberFormat("ru-RU").format(file.words)} сл.
      </span>

      <button
        onClick={onRemove}
        style={{
          background: "transparent",
          border: "none",
          cursor: "pointer",
          color: "var(--v4-ink-3)",
          padding: 6,
          display: "inline-flex",
        }}
      >
        <Icons.x />
      </button>
    </div>
  );
}
