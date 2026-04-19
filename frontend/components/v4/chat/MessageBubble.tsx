"use client";

/**
 * MessageBubble — generic chat bubble wrapper used for plain-text turns.
 *
 * Role → position/colour mapping:
 *   user       → right-aligned, neutral warm bubble
 *   assistant  → left-aligned, surface with 1px border
 *   system     → full-width, dashed muted panel (for non-conversational info)
 *
 * Complex payloads (prompt, critique, report, upload) render their own
 * specialised components; this one is for plain prose only.
 */

import type { ReactNode } from "react";

export type MessageRole = "user" | "assistant" | "system";

export function MessageBubble({
  role,
  children,
  meta,
  maxWidth,
}: {
  role: MessageRole;
  children: ReactNode;
  meta?: string;
  maxWidth?: number | string;
}) {
  const isUser = role === "user";
  const isSystem = role === "system";

  const align: "flex-end" | "flex-start" | "stretch" = isUser
    ? "flex-end"
    : isSystem
    ? "stretch"
    : "flex-start";

  return (
    <div
      className="vc-reveal"
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: align,
        width: "100%",
      }}
    >
      <div
        className={
          "vc-bubble " +
          (isUser
            ? "vc-bubble-user"
            : isSystem
            ? "vc-bubble-system"
            : "vc-bubble-assistant")
        }
        style={{
          maxWidth: maxWidth ?? (isUser ? 560 : "100%"),
          width: isSystem ? "100%" : undefined,
        }}
      >
        {children}
      </div>
      {meta && (
        <div
          className="vc-mono"
          style={{
            marginTop: 6,
            paddingLeft: isUser ? 0 : 4,
            paddingRight: isUser ? 4 : 0,
          }}
        >
          {meta}
        </div>
      )}
    </div>
  );
}

/**
 * Thinking — three animated dots rendered as a left-aligned assistant
 * bubble with an optional status message. Used for analyzing/synthesizing.
 */
export function Thinking({ label }: { label?: string }) {
  return (
    <div
      className="vc-reveal"
      style={{ display: "flex", alignItems: "flex-start" }}
    >
      <div
        className="vc-bubble vc-bubble-assistant"
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 12,
          color: "var(--vc-muted)",
          fontSize: 14,
        }}
      >
        <span style={{ display: "inline-flex", gap: 4, color: "var(--vc-muted)" }}>
          <span className="vc-dot" />
          <span className="vc-dot" />
          <span className="vc-dot" />
        </span>
        {label && <span>{label}</span>}
      </div>
    </div>
  );
}
