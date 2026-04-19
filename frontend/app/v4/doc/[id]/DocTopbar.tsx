"use client";

/** DocTopbar — sticky masthead for the Swiss document view */

const STEP_LABELS = ["Вопрос", "Промт", "Загрузка", "Критика", "Добор", "Финал"];

interface Props {
  question: string;
  step: number;
  cost: number;
  onExport: () => void;
  onNewSession: () => void;
}

export function DocTopbar({ question, step, cost, onExport, onNewSession }: Props) {
  /* TODO: no api binding — cost sparkline has no history endpoint, using static SVG */
  const sparkBars = [4, 7, 5, 9, 12, 8, 15, cost > 0 ? Math.min(cost / 5, 20) : 10];
  const maxBar = Math.max(...sparkBars, 1);

  return (
    <div className="vd-topbar">
      {/* Brand */}
      <div className="vd-brand">
        <div className="vd-brand-mark">SR</div>
        <span className="vd-brand-name">Smart Report</span>
        <span style={{
          fontFamily: "var(--vd-f-mono)",
          fontSize: 8,
          letterSpacing: "0.12em",
          border: "1px solid var(--vd-accent)",
          color: "var(--vd-accent-ink)",
          padding: "1px 5px",
        }}>V.IV</span>
      </div>

      {/* Center: session title (editable-look) + step indicator */}
      <div className="vd-topbar-center">
        <span className="vd-session-title" title={question}>
          {question.length > 60 ? question.slice(0, 60) + "…" : question}
        </span>
        <div className="vd-stepper" aria-label="прогресс">
          {STEP_LABELS.map((label, i) => {
            const n = i + 1;
            const active = n === step;
            const done = n < step;
            return (
              <div key={n} style={{ display: "flex", alignItems: "center", gap: 0 }}>
                <span
                  className={`vd-step ${active ? "active" : done ? "done" : ""}`}
                  title={label}
                >
                  {String(n).padStart(2, "0")}
                </span>
                {n < STEP_LABELS.length && <span className="vd-step-sep" />}
              </div>
            );
          })}
        </div>
      </div>

      {/* Right: cost badge + sparkline + export + new */}
      <div className="vd-topbar-right">
        {cost > 0 && (
          <div className="vd-cost-btn">
            <svg
              className="vd-sparkline"
              width={40}
              height={16}
              viewBox={`0 0 ${sparkBars.length * 5} 16`}
            >
              {sparkBars.map((v, i) => {
                const h = Math.max(2, Math.round((v / maxBar) * 14));
                return (
                  <rect
                    key={i}
                    x={i * 5}
                    y={16 - h}
                    width={3}
                    height={h}
                    opacity={i === sparkBars.length - 1 ? 1 : 0.35}
                  />
                );
              })}
            </svg>
            <span className="num">{Math.round(cost)}&nbsp;₽</span>
          </div>
        )}

        {step >= 6 && (
          <button className="vd-topbar-btn" onClick={onExport}>
            Экспорт ↓
          </button>
        )}

        <button className="vd-topbar-btn" onClick={onNewSession}>
          + Новый
        </button>
      </div>
    </div>
  );
}
