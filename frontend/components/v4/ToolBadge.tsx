"use client";

import { TOOL_DEFS } from "./ToolMark";

export function ToolBadge({
  tool,
  emphasized = false,
  small = false,
}: {
  tool: string;
  emphasized?: boolean;
  small?: boolean;
}) {
  const def = TOOL_DEFS[tool] || TOOL_DEFS.other;
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 8,
        padding: small ? "4px 8px" : "6px 10px",
        border: `1px solid ${emphasized ? "var(--v4-accent)" : "var(--v4-rule-strong)"}`,
        background: emphasized ? "var(--v4-accent-wash)" : "transparent",
        color: emphasized ? "var(--v4-accent-ink)" : "var(--v4-ink-2)",
      }}
    >
      <span
        style={{
          fontFamily: "var(--v4-f-mono)",
          fontSize: 9,
          letterSpacing: "0.1em",
          padding: "1px 4px",
          border: `1px solid ${emphasized ? "var(--v4-accent)" : "var(--v4-rule-strong)"}`,
        }}
      >
        {def.mark}
      </span>
      <span style={{ fontSize: small ? 11 : 12, fontWeight: 500 }}>{def.label}</span>
    </span>
  );
}
