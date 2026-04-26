"use client";

/** Section 03 — UPLOAD: drag-drop area + file list + run analysis button */

import { useRef, useState } from "react";
import { type V4Session } from "@/lib/apiV4";

interface Props {
  session: V4Session;
  uploading: boolean;
  analyzing: boolean;
  onUpload: (files: File[]) => void;
  onAnalyze: () => void;
}

export function SectionUpload({ session, uploading, analyzing, onUpload, onAnalyze }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const files = session.source_reports;
  const hasFiles = files.length > 0;
  const alreadyAnalyzed = session.status === "analyzed" || session.status === "dobor_uploaded" || session.status === "synthesized";

  function handleFiles(list: FileList | null) {
    if (!list || list.length === 0) return;
    onUpload(Array.from(list));
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    handleFiles(e.dataTransfer.files);
  }

  return (
    <section className="vd-section">
      <div className="vd-section-kicker">
        <span className="vd-kicker-num">03</span>
        Внешние отчёты
      </div>
      <h2 className="vd-h2">Загрузка результатов исследования</h2>

      <p className="vd-p" style={{ color: "var(--vd-ink-3)" }}>
        Запустите промт в рекомендованных инструментах, скачайте результаты и загрузите сюда. Поддерживаются .md, .txt, .pdf.
      </p>

      {/* Dropzone */}
      {!alreadyAnalyzed && (
        <>
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
              {uploading ? "Загружаем…" : "Перетащите файлы или нажмите для выбора"}
            </div>
            <div className="vd-dropzone-small">.md, .txt, .pdf · до 2 МБ · до 10 файлов</div>
            {uploading && <div className="vd-progress" style={{ marginTop: 12 }} />}
          </div>
        </>
      )}

      {/* File list */}
      {hasFiles && (
        <>
          <div style={{
            fontFamily: "var(--vd-f-mono)",
            fontSize: 10,
            letterSpacing: "0.08em",
            textTransform: "uppercase",
            color: "var(--vd-ink-3)",
            marginTop: 18,
            marginBottom: 8,
          }}>
            Принятые файлы
          </div>
          <div className="vd-file-grid">
            {files.map((f, i) => (
              <div key={i} className="vd-file-card">
                <div className="fn">{f.filename}</div>
                <div className="meta">
                  <span>{f.word_count > 0 ? `${f.word_count.toLocaleString("ru-RU")} сл.` : f.detected_tool ?? "файл"}</span>
                  <span className="ok">✓ принят</span>
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {/* Analyze button */}
      {hasFiles && !alreadyAnalyzed && (
        <div className="vd-actions" style={{ marginTop: 24 }}>
          <button
            className="vd-btn-primary"
            onClick={onAnalyze}
            disabled={analyzing || uploading}
          >
            {analyzing ? (
              <>
                <span className="vd-dots">
                  <span className="vd-dot" />
                  <span className="vd-dot" />
                  <span className="vd-dot" />
                </span>
                Анализируем…
              </>
            ) : (
              "→ Запустить анализ"
            )}
          </button>
          <span style={{ fontFamily: "var(--vd-f-mono)", fontSize: 10, color: "var(--vd-ink-4)", letterSpacing: "0.04em" }}>
            {files.length} {files.length === 1 ? "файл" : "файлов"}
          </span>
        </div>
      )}

      {alreadyAnalyzed && (
        <div style={{
          marginTop: 16,
          fontFamily: "var(--vd-f-mono)",
          fontSize: 11,
          color: "var(--vd-ok)",
          display: "flex",
          alignItems: "center",
          gap: 8,
        }}>
          <span>✓</span> Анализ завершён — результаты в разделе 04
        </div>
      )}
    </section>
  );
}
