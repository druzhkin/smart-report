"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import { getSession, uploadFollowup, synthesize, type V4Session } from "@/lib/apiV4";
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

export default function V4DoborPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = params?.id || "";
  const { setCost } = useCost();

  const [session, setSession] = useState<V4Session | null>(null);
  const [files, setFiles] = useState<UIFile[]>([]);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [events, setEvents] = useState<UIEvent[]>([]);
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
      if (files.length) await uploadFollowup(id, files.map((f) => f.file));
      setEvents((e) => [
        ...e,
        { event: "synthesizer", message: "Собираю финальный отчёт" },
      ]);
      await synthesize(id);
      router.push(`/v4/session/${id}/report`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Не удалось собрать финал");
      setBusy(false);
    }
  }

  if (busy) {
    return <ProcessingOverlay stage="synthesizer" />;
  }

  const a = session?.analysis;
  // v4.1+: prefer single consolidated prompt; fall back to legacy MUST list.
  const singleFollowup = a?.followup_prompt ?? null;
  const mustFollowups = singleFollowup
    ? []
    : (a?.followup_prompts.filter((f) => f.priority === "must") ?? []);
  const fileCount = files.length;
  // Progress denominator: 1 if single prompt, else count of MUST items.
  const doborTotal = singleFollowup ? 1 : mustFollowups.length;
  const progressPct = doborTotal > 0 ? Math.min(100, (fileCount / doborTotal) * 100) : 0;

  return (
    <div
      className="v4-container"
      style={{ paddingTop: 48, paddingBottom: 96, position: "relative", zIndex: 1 }}
    >
      {/* Breadcrumb */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 32 }}>
        <span className="v4-mono" style={{ color: "var(--v4-ink-4)" }}>Критика / </span>
        <span className="v4-mono">Добор</span>
        <span style={{ width: 16, height: 1, background: "var(--v4-rule-strong)" }} />
        <span className="v4-mono" style={{ color: "var(--v4-ink-4)" }}>Синтез →</span>
      </div>

      <SectionKicker number="05">Загрузка добора</SectionKicker>
      <h1
        className="v4-display v4-display-l"
        style={{ marginTop: 18, marginBottom: 16, maxWidth: 780 }}
      >
        Вы закрыли пробелы — загрузите отчёты по&nbsp;followup-промтам.
      </h1>

      {/* Progress banner */}
      <div
        style={{
          marginTop: 8,
          marginBottom: 32,
          padding: "16px 20px",
          border: "1px solid var(--v4-rule)",
          background: "var(--v4-paper-2)",
          display: "grid",
          gridTemplateColumns: "1fr auto",
          gap: 24,
          alignItems: "center",
        }}
      >
        <div>
          <div className="v4-mono" style={{ marginBottom: 6 }}>Прогресс добора</div>
          <div style={{ fontFamily: "var(--v4-f-display)", fontSize: 22, color: "var(--v4-ink)" }}>
            {singleFollowup
              ? `Загружено ${fileCount} из 1 добора`
              : `Загружено ${fileCount} из ${doborTotal} обязательных`}
          </div>
        </div>
        <div
          style={{
            width: 280,
            height: 6,
            background: "var(--v4-paper-3)",
            position: "relative",
          }}
        >
          <div
            style={{
              position: "absolute",
              inset: 0,
              width: `${progressPct}%`,
              background: "var(--v4-accent)",
            }}
          />
        </div>
      </div>

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
          {/* Drop zone */}
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
              padding: "40px 32px",
              textAlign: "center",
              cursor: "pointer",
              transition: "all .15s ease",
            }}
          >
            <div style={{ display: "inline-flex", flexDirection: "column", alignItems: "center", gap: 10 }}>
              <Icons.upload style={{ color: "var(--v4-ink-3)" }} />
              <div style={{ fontFamily: "var(--v4-f-display)", fontSize: 22, color: "var(--v4-ink)", marginTop: 6 }}>
                Перетащите доборные отчёты
              </div>
              <div style={{ color: "var(--v4-ink-3)", fontSize: 13 }}>
                или <span style={{ textDecoration: "underline" }}>выберите файлы</span>
              </div>
              <div className="v4-mono" style={{ marginTop: 4 }}>.md · .markdown · .txt</div>
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

          {/* File list */}
          {files.length > 0 && (
            <div style={{ marginTop: 20, display: "flex", flexDirection: "column", gap: 0 }}>
              {files.map((f) => (
                <div
                  key={f.id}
                  style={{
                    display: "grid",
                    gridTemplateColumns: "auto 1fr auto",
                    gap: 16,
                    alignItems: "center",
                    padding: "12px 0",
                    borderTop: "1px solid var(--v4-rule)",
                  }}
                >
                  <ToolMark tool={f.tool} size={22} />
                  <span style={{ fontSize: 14, color: "var(--v4-ink)" }}>{f.name}</span>
                  <button
                    onClick={() => setFiles(files.filter((x) => x.id !== f.id))}
                    style={{
                      background: "transparent",
                      border: "none",
                      cursor: "pointer",
                      color: "var(--v4-ink-3)",
                      display: "inline-flex",
                    }}
                  >
                    <Icons.x />
                  </button>
                </div>
              ))}
            </div>
          )}

          <div
            style={{
              marginTop: 16,
              padding: "12px 16px",
              background: "var(--v4-paper-3)",
              fontSize: 13,
              color: "var(--v4-ink-3)",
            }}
          >
            Можно пропустить добор — Synthesizer соберёт финал и&nbsp;на&nbsp;исходных отчётах.
            Но&nbsp;глубина будет ниже.
          </div>

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
            <button
              className="v4-btn v4-btn-ghost"
              onClick={() => router.push(`/v4/session/${id}/analysis`)}
              style={{ fontSize: 13 }}
            >
              <Icons.arrowLeft /> Назад к критике
            </button>
            <button
              className="v4-btn v4-btn-primary"
              onClick={run}
              disabled={busy}
            >
              {files.length > 0 ? "Синтезировать финальный отчёт" : "Синтезировать без добора"}
              <Icons.arrowRight />
            </button>
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
            phaseStatus={{ prompt: "done", external: "done", analyzer: "done", synth: "pending" }}
          />

          {/* Single consolidated prompt reminder (v4.1+) */}
          {singleFollowup && (
            <div style={{ marginTop: 32 }}>
              <SectionKicker>Напомнить добор-промт</SectionKicker>
              <div
                style={{
                  marginTop: 12,
                  padding: "10px 0",
                  borderBottom: "1px solid var(--v4-rule)",
                  display: "grid",
                  gridTemplateColumns: "1fr auto",
                  gap: 10,
                  alignItems: "center",
                }}
              >
                <span style={{ fontSize: 13, color: "var(--v4-ink-2)" }}>
                  {singleFollowup.target_info || "Сводный добор-промт"}
                </span>
                <ToolMark tool={singleFollowup.suggested_tool} size={20} />
              </div>
            </div>
          )}

          {/* Legacy: multiple MUST followup reminders */}
          {!singleFollowup && mustFollowups.length > 0 && (
            <div style={{ marginTop: 32 }}>
              <SectionKicker>Напомнить followup-промты</SectionKicker>
              <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 10 }}>
                {mustFollowups.map((f, i) => (
                  <div
                    key={f.prompt_id}
                    style={{
                      display: "grid",
                      gridTemplateColumns: "24px 1fr auto",
                      gap: 10,
                      alignItems: "center",
                      padding: "10px 0",
                      borderBottom: "1px solid var(--v4-rule)",
                    }}
                  >
                    <span
                      style={{
                        fontFamily: "var(--v4-f-mono)",
                        fontVariantNumeric: "tabular-nums",
                        fontSize: 11,
                        color: "var(--v4-ink-3)",
                      }}
                    >
                      0{i + 1}
                    </span>
                    <span style={{ fontSize: 13, color: "var(--v4-ink-2)" }}>
                      {f.target_info}
                    </span>
                    <ToolMark tool={f.suggested_tool} size={20} />
                  </div>
                ))}
              </div>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
