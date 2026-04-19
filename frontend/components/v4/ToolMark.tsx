"use client";

// ToolMark — 2-letter mono abbreviation in a hairline square.
// Sizes: 20 / 22 / 28 (default 22).

export type ToolKey = "perplexity" | "openai" | "openai_dr" | "claude" | "other";

export const TOOL_DEFS: Record<string, { label: string; mark: string; hint: string }> = {
  perplexity: { label: "Perplexity DR", mark: "PX", hint: "Perplexity Deep Research" },
  openai:     { label: "OpenAI DR",     mark: "OA", hint: "OpenAI Deep Research" },
  openai_dr:  { label: "OpenAI DR",     mark: "OA", hint: "OpenAI Deep Research" },
  claude:     { label: "Claude R",      mark: "CL", hint: "Claude Research" },
  other:      { label: "Другое",        mark: "··", hint: "Другой источник" },
};

export function ToolMark({ tool, size = 22 }: { tool: string; size?: number }) {
  const def = TOOL_DEFS[tool] || TOOL_DEFS.other;
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        width: size,
        height: size,
        border: "1px solid var(--v4-rule-emphatic)",
        fontFamily: "var(--v4-f-mono)",
        fontSize: size * 0.38,
        letterSpacing: "0.04em",
        background: "var(--v4-paper-2)",
        color: "var(--v4-ink-2)",
        fontWeight: 500,
        flexShrink: 0,
      }}
      title={def.hint}
    >
      {def.mark}
    </span>
  );
}
