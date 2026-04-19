"use client";

/**
 * StatusBar — thin sticky header for the chat route.
 *
 * Shows: product mark · current stage (e.g. "Шаг 2 · Анализ") · running cost
 * · ghost "Новое исследование" button.  Hides itself below 44px height.
 * Uses useCost() so it reflects backend total_cost_rub in real time.
 */

import { useCost } from "@/lib/costContext";
import { Plus } from "lucide-react";

export type StatusStage = {
  step: number;
  total: number;
  label: string;
};

export function StatusBar({
  stage,
  running = false,
  onNewResearch,
}: {
  stage: StatusStage;
  running?: boolean;
  onNewResearch?: () => void;
}) {
  const { cost } = useCost();

  return (
    <header
      style={{
        flexShrink: 0,
        height: 48,
        borderBottom: "1px solid var(--vc-border)",
        background: "rgba(250, 250, 249, 0.85)",
        backdropFilter: "blur(12px)",
        WebkitBackdropFilter: "blur(12px)",
        display: "flex",
        alignItems: "center",
        padding: "0 20px",
        gap: 16,
      }}
    >
      {/* Product mark */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
        }}
      >
        <span
          style={{
            width: 8,
            height: 8,
            borderRadius: 2,
            background: "var(--vc-text)",
            display: "inline-block",
          }}
        />
        <span
          style={{
            fontSize: 13,
            fontWeight: 600,
            letterSpacing: "-0.01em",
          }}
        >
          Smart Report
        </span>
      </div>

      <span
        style={{
          width: 1,
          height: 16,
          background: "var(--vc-border)",
          flexShrink: 0,
        }}
      />

      {/* Stage */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          flex: 1,
          minWidth: 0,
        }}
      >
        <span className="vc-mono" style={{ flexShrink: 0 }}>
          {String(stage.step).padStart(2, "0")} / {String(stage.total).padStart(2, "0")}
        </span>
        <span
          style={{
            fontSize: 13,
            color: "var(--vc-text)",
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
        >
          {stage.label}
        </span>
        {running && (
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 3,
              color: "var(--vc-muted)",
              marginLeft: 4,
            }}
          >
            <span className="vc-dot" />
            <span className="vc-dot" />
            <span className="vc-dot" />
          </span>
        )}
      </div>

      {/* Right side — cost + new research */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          flexShrink: 0,
        }}
      >
        {cost !== null && cost > 0 && (
          <span
            style={{
              fontFamily: "var(--vc-f-mono)",
              fontVariantNumeric: "tabular-nums",
              fontSize: 12,
              color: "var(--vc-muted)",
            }}
          >
            {cost} ₽
          </span>
        )}
        {onNewResearch && (
          <button
            type="button"
            className="vc-btn vc-btn-ghost vc-btn-sm"
            onClick={onNewResearch}
            aria-label="Новое исследование"
          >
            <Plus size={14} strokeWidth={1.75} />
            <span>Новое</span>
          </button>
        )}
      </div>
    </header>
  );
}
