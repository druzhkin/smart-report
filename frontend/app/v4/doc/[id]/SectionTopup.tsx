"use client";

/** Section 05 — TOPUP: followup prompt + upload dobor + synthesize */

import { useRef, useState } from "react";
import { type V4Session } from "@/lib/apiV4";

interface Props {
  session: V4Session;
  uploading: boolean;
  synthesizing: boolean;
  onUpload: (files: File[]) => void;
  onSynthesize: () => void;
}

export function SectionTopup({ session, uploading, synthesizing, onUpload, onSynthesize }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const analysis = session.analysis;

  const alreadySynthesized = session.status === "synthesized";
  const hasFollowup = session.followup_reports.length > 0;

  /* Canonical followup: single consolidated prompt (v4.1+) */
  const followup = analysis?.followup_prompt ?? analysis?.followup_prompts?.[0] ?? null;

  function handleFiles(list: FileList | null) {
    if (!list || list.length === 0) return;
    onUpload(Array.from(list));
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    handleFiles(e.dataTransfer.files);
  }

  if (!analysis) return null;

  return (
    <section className="vd-section">
      <div className="vd-section-kicker">
        <span className="vd-kicker-num">05</span>
        Добор данных
      </div>
      <h2 className="vd-h2">Уточняющий запрос и добор</h2>

      {/* Followup prompt block */}
      {followup ? (
        <div className="vd-followup-box">
          <div className="vd-followup-label">
            Добор-промт · {followup.intent === "fill_gap" ? "заполнение пробелов" : followup.intent === "verify_number" ? "верификация цифр" : "разрешение конфликтов"}
          </div>
          <div className="vd-followup-text">{followup.prompt}</div>
          {followup.target_info && (
            <div style={{
              marginTop: 12,
              fontFamily: "var(--vd-f-mono)",
              fontSize: 11,
              color: "var(--vd-ink-3)",
              letterSpacing: "0.02em",
            }}>
              Целевая информация: {followup.target_info}
            </div>
          )}
          {followup.suggested_tool && (
            <div style={{ marginTop: 8, display: "flex", gap: 8, alignItems: "center" }}>
              <span style={{
                fontFamily: "var(--vd-f-mono)",
                fontSize: 10,
                letterSpacing: "0.08em",
                textTransform: "uppercase",
                color: "var(--vd-ink-4)",
              }}>
                Инструмент:
              </span>
              <span className="vd-tool-chip top" style={{ fontSize: 12 }}>
                {followup.suggested_tool === "perplexity" ? "Perplexity DR" :
                 followup.suggested_tool === "openai_dr" ? "OpenAI DR" : "Claude Research"}
              </span>
              {followup.priority === "must" && (
                <span style={{
                  fontFamily: "var(--vd-f-mono)",
                  fontSize: 9,
                  letterSpacing: "0.1em",
                  padding: "2px 6px",
                  background: "var(--vd-bad)",
                  color: "#fff",
                  textTransform: "uppercase",
                  fontWeight: 700,
                }}>
                  Обязательно
                </span>
              )}
            </div>
          )}
        </div>
      ) : (
        <div className="vd-followup-box" style={{ borderColor: "var(--vd-rule)" }}>
          <div style={{ fontFamily: "var(--vd-f-mono)", fontSize: 12, color: "var(--vd-ink-3)" }}>
            Добор-промт недоступен. Загрузите дополнительные источники и запустите синтез.
          </div>
        </div>
      )}

      {/* Upload followup files */}
      {!alreadySynthesized && (
        <>
          <div style={{ marginTop: 24, marginBottom: 12 }}>
            <div style={{
              fontFamily: "var(--vd-f-mono)",
              fontSize: 10,
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              color: "var(--vd-ink-3)",
              marginBottom: 12,
            }}>
              Загрузить результаты добора
            </div>
            <input
              ref={inputRef}
              type="file"
              multiple
              accept=".md,.txt,.pdf"
              style={{ display: "none" }}
              onChange={(e) => handleFiles(e.target.files)}
            />
            <div
              className={`vd-dropzone${dragging ? " dragging" : ""}`}
              onClick={() => inputRef.current?.click()}
              onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onDrop={handleDrop}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => e.key === "Enter" && inputRef.current?.click()}
            >
              <div className="vd-dropzone-big">
                {uploading ? "Загружаем…" : "Добавить результаты уточнённого запроса"}
              </div>
              <div className="vd-dropzone-small">.md, .txt, .pdf · до 2 МБ · до 5 файлов</div>
              {uploading && <div className="vd-progress" style={{ marginTop: 12 }} />}
            </div>
          </div>

          {/* Uploaded followup files */}
          {hasFollowup && (
            <div className="vd-file-grid" style={{ marginBottom: 16 }}>
              {session.followup_reports.map((f, i) => (
                <div key={i} className="vd-file-card">
                  <div className="fn">{f.filename}</div>
                  <div className="meta">
                    <span>{f.word_count > 0 ? `${f.word_count.toLocaleString("ru-RU")} сл.` : f.detected_tool ?? "файл"}</span>
                    <span className="ok">✓ принят</span>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Synthesize button */}
          <div className="vd-actions">
            <button
              className="vd-btn-primary"
              onClick={onSynthesize}
              disabled={synthesizing || uploading}
            >
              {synthesizing ? (
                <>
                  <span className="vd-dots">
                    <span className="vd-dot" />
                    <span className="vd-dot" />
                    <span className="vd-dot" />
                  </span>
                  Синтезируем отчёт…
                </>
              ) : (
                "→ Синтезировать финальный отчёт"
              )}
            </button>
            {!hasFollowup && (
              <span style={{ fontFamily: "var(--vd-f-mono)", fontSize: 10, color: "var(--vd-ink-4)", letterSpacing: "0.04em" }}>
                Можно без добора
              </span>
            )}
          </div>
          {synthesizing && <div className="vd-progress" />}
        </>
      )}

      {alreadySynthesized && (
        <div style={{
          marginTop: 16,
          fontFamily: "var(--vd-f-mono)",
          fontSize: 11,
          color: "var(--vd-ok)",
          display: "flex",
          alignItems: "center",
          gap: 8,
        }}>
          <span>✓</span> Синтез завершён — откройте раздел 06 для финального отчёта
        </div>
      )}
    </section>
  );
}
