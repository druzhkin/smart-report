"use client";

// Masthead — sticky double-rule header for v4 screens 1–5.
// Screen 6 has its own document masthead, so pass showOn6={false} from layout.

import { usePathname, useRouter } from "next/navigation";

const STEP_LABELS = ["Новое", "Промт", "Загрузка", "Критика", "Добор", "Финал"];

function getStep(pathname: string): number {
  if (/\/new/.test(pathname)) return 1;
  if (/\/prompt/.test(pathname)) return 2;
  if (/\/upload/.test(pathname)) return 3;
  if (/\/analysis/.test(pathname)) return 4;
  if (/\/dobor/.test(pathname)) return 5;
  if (/\/report/.test(pathname)) return 6;
  return 1;
}

/** doc routes have their own DocTopbar — suppress V4Shell masthead there */
function isDocRoute(pathname: string): boolean {
  return /\/v4\/doc/.test(pathname);
}

export function Masthead({
  cost,
  onReset,
}: {
  cost?: number | null;
  onReset?: () => void;
}) {
  const pathname = usePathname() || "";
  const step = getStep(pathname);
  const totalSteps = 6;

  // Screen 6 has its own document-style masthead; hide the chrome bar there
  if (step === 6) return null;

  // /v4/doc routes have their own DocTopbar — suppress this masthead
  if (isDocRoute(pathname)) return null;

  const dateStr = new Intl.DateTimeFormat("ru-RU", {
    day: "numeric",
    month: "long",
    year: "numeric",
  }).format(new Date());

  return (
    <header
      style={{
        borderTop: "1px solid var(--v4-rule-strong)",
        borderBottom: "1px solid var(--v4-rule-strong)",
        padding: "14px 0",
        background: "rgba(255,255,255,0.85)",
        backdropFilter: "blur(14px)",
        WebkitBackdropFilter: "blur(14px)",
        position: "sticky",
        top: 0,
        zIndex: 10,
      }}
    >
      <div
        style={{
          maxWidth: 1440,
          margin: "0 auto",
          padding: "0 48px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 24,
        }}
      >
        {/* Brand */}
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <div
            style={{
              fontFamily: "var(--v4-f-display)",
              fontSize: 26,
              letterSpacing: "-0.02em",
              lineHeight: 1,
              color: "var(--v4-ink)",
            }}
          >
            Smart Report
            <span
              style={{
                fontFamily: "var(--v4-f-mono)",
                fontSize: 9,
                marginLeft: 10,
                verticalAlign: "middle",
                padding: "2px 6px",
                border: "1px solid var(--v4-accent)",
                color: "var(--v4-accent-ink)",
                letterSpacing: "0.14em",
              }}
            >
              V.IV
            </span>
          </div>
          <span
            style={{
              fontFamily: "var(--v4-f-mono)",
              fontSize: 11,
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              color: "var(--v4-ink-4)",
            }}
          >
            {dateStr}
          </span>
        </div>

        {/* Step stepper */}
        <nav
          aria-label="прогресс"
          style={{ display: "flex", alignItems: "center", gap: 12 }}
        >
          {Array.from({ length: totalSteps }).map((_, i) => {
            const n = i + 1;
            const active = n === step;
            const done = n < step;
            return (
              <div
                key={n}
                style={{ display: "flex", alignItems: "center", gap: 8 }}
              >
                <span
                  style={{
                    fontFamily: "var(--v4-f-mono)",
                    fontVariantNumeric: "tabular-nums",
                    fontSize: 11,
                    color: active
                      ? "var(--v4-accent-ink)"
                      : done
                      ? "var(--v4-ink-2)"
                      : "var(--v4-ink-4)",
                    fontWeight: active ? 500 : 400,
                    borderBottom: active
                      ? "1px solid var(--v4-accent)"
                      : "1px solid transparent",
                    paddingBottom: 4,
                  }}
                >
                  {String(n).padStart(2, "0")}
                </span>
                {n < totalSteps && (
                  <span
                    style={{
                      width: 8,
                      height: 1,
                      background: "var(--v4-rule)",
                    }}
                  />
                )}
              </div>
            );
          })}
        </nav>

        {/* Right: cost + reset */}
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          {cost != null && cost > 0 && (
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span
                style={{
                  fontFamily: "var(--v4-f-mono)",
                  fontSize: 10,
                  letterSpacing: "0.08em",
                  textTransform: "uppercase",
                  color: "var(--v4-ink-3)",
                }}
              >
                Сессия
              </span>
              <span
                className="v4-mono-n"
                style={{
                  fontSize: 14,
                  fontWeight: 500,
                  color: "var(--v4-ink)",
                }}
              >
                {Math.round(cost)}&nbsp;₽
              </span>
            </div>
          )}
          {onReset && (
            <button
              onClick={onReset}
              style={{
                background: "transparent",
                border: "none",
                cursor: "pointer",
                fontFamily: "var(--v4-f-body)",
                fontSize: 12,
                color: "var(--v4-ink-2)",
                padding: "8px 10px",
              }}
            >
              Начать заново
            </button>
          )}
        </div>
      </div>
    </header>
  );
}
