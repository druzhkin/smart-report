"use client";

/**
 * Composer — single-line / auto-growing textarea pinned to the bottom of the
 * chat. Cmd/Ctrl+Enter or click-send submits. Placeholder adapts to stage.
 *
 * This is the TEXT composer; when the stage requires file upload the parent
 * renders <UploadComposer/> instead.
 */

import { useEffect, useRef, useState } from "react";
import { ArrowUp } from "lucide-react";

const MAX_ROWS = 6;
const LINE_HEIGHT = 22; // px — matches 15px/1.5 in the textarea

export function Composer({
  placeholder = "Задайте вопрос…",
  onSubmit,
  disabled = false,
  busy = false,
  autoFocus = false,
  helper,
}: {
  placeholder?: string;
  onSubmit: (text: string) => void;
  disabled?: boolean;
  busy?: boolean;
  autoFocus?: boolean;
  helper?: string;
}) {
  const [value, setValue] = useState("");
  const taRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = taRef.current;
    if (!el) return;
    el.style.height = "auto";
    const maxH = LINE_HEIGHT * MAX_ROWS + 28; // + vertical padding
    el.style.height = `${Math.min(el.scrollHeight, maxH)}px`;
  }, [value]);

  useEffect(() => {
    if (autoFocus) taRef.current?.focus();
  }, [autoFocus]);

  function submit() {
    const t = value.trim();
    if (!t || disabled || busy) return;
    onSubmit(t);
    setValue("");
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      e.preventDefault();
      submit();
    }
  }

  const canSend = !!value.trim() && !disabled && !busy;

  return (
    <div
      style={{
        position: "relative",
        display: "flex",
        alignItems: "flex-end",
        gap: 8,
        padding: "2px 2px 2px 2px",
        background: "var(--vc-surface)",
        border: "1px solid var(--vc-border)",
        borderRadius: 16,
        transition: "border-color 140ms ease, box-shadow 140ms ease",
      }}
    >
      <textarea
        ref={taRef}
        className="vc-textarea"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={onKeyDown}
        placeholder={placeholder}
        disabled={disabled || busy}
        rows={1}
        style={{
          border: "none",
          background: "transparent",
          padding: "12px 14px",
          margin: 0,
          minHeight: 44,
          boxShadow: "none",
        }}
      />
      <button
        type="button"
        onClick={submit}
        disabled={!canSend}
        aria-label="Отправить (Cmd/Ctrl+Enter)"
        className="vc-btn vc-btn-primary"
        style={{
          width: 40,
          height: 40,
          padding: 0,
          borderRadius: 12,
          flexShrink: 0,
          margin: 4,
        }}
      >
        <ArrowUp size={16} strokeWidth={2} />
      </button>
      {helper && (
        <span
          className="vc-mono"
          style={{
            position: "absolute",
            right: 56,
            bottom: -22,
            fontSize: 11,
          }}
        >
          {helper}
        </span>
      )}
    </div>
  );
}
