"use client";

import { useState } from "react";
import { Icons } from "./Icon";

export function Collapsible({
  title,
  defaultOpen = false,
  right,
  children,
  kicker,
}: {
  title: string;
  defaultOpen?: boolean;
  right?: React.ReactNode;
  children: React.ReactNode;
  kicker?: string;
}) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div style={{ borderTop: "1px solid var(--v4-rule)" }}>
      <button
        onClick={() => setOpen(!open)}
        style={{
          width: "100%",
          background: "transparent",
          border: "none",
          padding: "18px 0",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          cursor: "pointer",
          fontFamily: "var(--v4-f-body)",
          textAlign: "left",
        }}
      >
        <div style={{ display: "flex", alignItems: "baseline", gap: 12 }}>
          {kicker && (
            <span
              style={{
                fontFamily: "var(--v4-f-mono)",
                fontSize: 10,
                letterSpacing: "0.08em",
                textTransform: "uppercase",
                color: "var(--v4-ink-3)",
              }}
            >
              {kicker}
            </span>
          )}
          <span
            style={{
              fontFamily: "var(--v4-f-display)",
              fontWeight: 400,
              fontSize: 22,
              letterSpacing: "-0.01em",
              lineHeight: 1.02,
              color: "var(--v4-ink)",
            }}
          >
            {title}
          </span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          {right}
          <span
            style={{
              display: "inline-flex",
              transform: open ? "rotate(180deg)" : "none",
              transition: "transform .2s",
              color: "var(--v4-ink-3)",
            }}
          >
            <Icons.chevronDown />
          </span>
        </div>
      </button>
      {open && (
        <div
          style={{ paddingBottom: 24, animation: "v4FadeIn .35s ease both" }}
        >
          {children}
        </div>
      )}
    </div>
  );
}
