"use client";

/**
 * UploadComposer — file-drop zone styled like a chat composer. Takes the
 * Composer's slot at stages 3 (reports) and 7 (followup).
 *
 * Auto-detects source tool by filename (perplexity / openai_dr / claude /
 * other), displays each file as a row with a tool chip, and ships a
 * "Send N reports" primary CTA that mirrors the Composer submit affordance.
 */

import { useCallback, useRef, useState } from "react";
import { Paperclip, X, FileText, ArrowUp } from "lucide-react";

type UIFile = {
  id: string;
  file: File;
  name: string;
  tool: "perplexity" | "openai_dr" | "claude" | "other";
  size: number;
};

const TOOL_LABEL: Record<UIFile["tool"], string> = {
  perplexity: "Perplexity",
  openai_dr: "OpenAI DR",
  claude: "Claude",
  other: "Файл",
};

function detectTool(filename: string): UIFile["tool"] {
  const f = filename.toLowerCase();
  if (f.includes("perplex") || f.includes("pplx")) return "perplexity";
  if (f.includes("openai") || f.includes("chatgpt") || f.includes("gpt") || f.includes("_dr")) return "openai_dr";
  if (f.includes("claude")) return "claude";
  return "other";
}

function formatSize(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export function UploadComposer({
  onSubmit,
  placeholder,
  busy = false,
  submitLabel,
  allowSkip = false,
  onSkip,
  skipLabel,
}: {
  onSubmit: (files: File[]) => void;
  placeholder?: string;
  busy?: boolean;
  submitLabel?: string;
  allowSkip?: boolean;
  onSkip?: () => void;
  skipLabel?: string;
}) {
  const [files, setFiles] = useState<UIFile[]>([]);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const add = useCallback((raw: FileList | File[] | null) => {
    if (!raw) return;
    const allowed = [".md", ".markdown", ".txt"];
    const list: UIFile[] = [];
    for (const f of Array.from(raw)) {
      if (!allowed.some((ext) => f.name.toLowerCase().endsWith(ext))) continue;
      list.push({
        id: Math.random().toString(36).slice(2),
        file: f,
        name: f.name,
        tool: detectTool(f.name),
        size: f.size,
      });
    }
    if (list.length) setFiles((prev) => [...prev, ...list]);
  }, []);

  const canSubmit = files.length > 0 && !busy;
  const n = files.length;
  const sendLabel = submitLabel ?? (n === 0 ? "Отправить" : `Отправить · ${n}`);

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 10,
      }}
    >
      {/* Drop zone */}
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          add(e.dataTransfer.files);
        }}
        onClick={() => inputRef.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") inputRef.current?.click();
        }}
        style={{
          border: `1px ${dragging ? "solid" : "dashed"} ${
            dragging ? "var(--vc-text)" : "var(--vc-border-s)"
          }`,
          background: dragging ? "var(--vc-surface-2)" : "var(--vc-surface)",
          borderRadius: 14,
          padding: "20px 20px",
          cursor: "pointer",
          transition: "border-color 140ms ease, background 140ms ease",
          display: "flex",
          alignItems: "center",
          gap: 14,
        }}
      >
        <span
          style={{
            width: 36,
            height: 36,
            borderRadius: 10,
            background: "var(--vc-surface-2)",
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            color: "var(--vc-muted)",
            flexShrink: 0,
          }}
        >
          <Paperclip size={16} strokeWidth={1.75} />
        </span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 14, color: "var(--vc-text)", fontWeight: 500 }}>
            {placeholder ?? "Перетащите отчёты или нажмите, чтобы выбрать"}
          </div>
          <div
            style={{
              fontSize: 12,
              color: "var(--vc-muted)",
              marginTop: 2,
            }}
          >
            .md · .markdown · .txt — инструмент определяется по имени файла
          </div>
        </div>
        <input
          ref={inputRef}
          type="file"
          accept=".md,.markdown,.txt"
          multiple
          hidden
          onChange={(e) => {
            add(e.target.files);
            if (inputRef.current) inputRef.current.value = "";
          }}
        />
      </div>

      {/* File list */}
      {files.length > 0 && (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 6,
          }}
        >
          {files.map((f) => (
            <div
              key={f.id}
              style={{
                display: "grid",
                gridTemplateColumns: "28px 1fr auto auto auto",
                gap: 12,
                alignItems: "center",
                padding: "10px 14px",
                background: "var(--vc-surface)",
                border: "1px solid var(--vc-border)",
                borderRadius: 10,
              }}
            >
              <FileText size={16} strokeWidth={1.5} style={{ color: "var(--vc-muted)" }} />
              <span
                style={{
                  fontSize: 13,
                  color: "var(--vc-text)",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
                title={f.name}
              >
                {f.name}
              </span>
              <span className="vc-chip">{TOOL_LABEL[f.tool]}</span>
              <span
                className="vc-mono"
                style={{ fontSize: 11, minWidth: 52, textAlign: "right" }}
              >
                {formatSize(f.size)}
              </span>
              <button
                type="button"
                onClick={() => setFiles((prev) => prev.filter((x) => x.id !== f.id))}
                aria-label="Удалить файл"
                className="vc-btn vc-btn-ghost"
                style={{
                  width: 28,
                  height: 28,
                  padding: 0,
                  borderRadius: 8,
                }}
              >
                <X size={14} strokeWidth={1.75} />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Actions row */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          paddingTop: 2,
        }}
      >
        <span className="vc-mono" style={{ fontSize: 11 }}>
          {files.length > 0
            ? `${files.length} ${files.length === 1 ? "файл" : "файла(ов)"} готово`
            : "добавьте хотя бы один файл"}
        </span>
        <div style={{ display: "flex", gap: 8 }}>
          {allowSkip && onSkip && (
            <button
              type="button"
              className="vc-btn vc-btn-ghost vc-btn-sm"
              onClick={onSkip}
              disabled={busy}
            >
              {skipLabel ?? "Пропустить"}
            </button>
          )}
          <button
            type="button"
            className="vc-btn vc-btn-primary vc-btn-sm"
            onClick={() => {
              if (!canSubmit) return;
              onSubmit(files.map((f) => f.file));
            }}
            disabled={!canSubmit}
          >
            <ArrowUp size={13} strokeWidth={2} />
            <span>{sendLabel}</span>
          </button>
        </div>
      </div>
    </div>
  );
}
