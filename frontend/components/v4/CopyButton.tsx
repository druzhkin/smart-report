"use client";

import { useState, useCallback } from "react";
import { Icons } from "./Icon";

export function CopyButton({
  text,
  label = "Копировать",
  variant = "ghost",
  style: extraStyle,
}: {
  text: string;
  label?: string;
  variant?: "ghost" | "boxed";
  style?: React.CSSProperties;
}) {
  const [copied, setCopied] = useState(false);

  const onClick = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const ta = document.createElement("textarea");
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }, [text]);

  const base: React.CSSProperties = {
    display: "inline-flex",
    alignItems: "center",
    gap: 8,
    fontFamily: "var(--v4-f-body)",
    fontSize: 12,
    fontWeight: 500,
    padding: "7px 12px",
    cursor: "pointer",
    transition: "all .15s",
    letterSpacing: "-0.002em",
    borderRadius: 0,
  };

  const style: React.CSSProperties =
    variant === "boxed"
      ? {
          ...base,
          border: "1px solid var(--v4-rule-emphatic)",
          background: copied ? "var(--v4-accent)" : "var(--v4-paper-3)",
          color: copied ? "var(--v4-paper)" : "var(--v4-ink)",
        }
      : {
          ...base,
          border: "1px solid transparent",
          background: copied ? "var(--v4-paper-3)" : "transparent",
          color: "var(--v4-ink-2)",
        };

  return (
    <button onClick={onClick} style={{ ...style, ...(extraStyle || {}) }}>
      {copied ? <Icons.check /> : <Icons.copy />}
      <span>{copied ? "Скопировано" : label}</span>
    </button>
  );
}
