"use client";

/** Section 01 — START: shows the original question and triggers prompt generation */

interface Props {
  question: string;
  loading: boolean;
  canProceed: boolean;
  alreadyDone: boolean;
  onGenerate: () => void;
}

export function SectionStart({ question, loading, alreadyDone, onGenerate }: Props) {
  return (
    <section className="vd-section">
      <div className="vd-section-kicker">
        <span className="vd-kicker-num">01</span>
        Исследовательский вопрос
      </div>
      <h2 className="vd-h2">Вопрос</h2>

      <div className="vd-prompt-box" style={{ marginBottom: 20 }}>
        <div className="vd-prompt-text">{question}</div>
      </div>

      {alreadyDone ? (
        <div style={{
          fontFamily: "var(--vd-f-mono)",
          fontSize: 11,
          color: "var(--vd-ok)",
          letterSpacing: "0.04em",
          display: "flex",
          alignItems: "center",
          gap: 8,
        }}>
          <span>✓</span> Промт сгенерирован — см. раздел 02
        </div>
      ) : (
        <>
          <p className="vd-p" style={{ color: "var(--vd-ink-3)", marginBottom: 16 }}>
            Система сформулирует детализированный research-промт и порекомендует инструменты для сбора данных.
          </p>
          <div className="vd-actions">
            <button
              className="vd-btn-primary"
              onClick={onGenerate}
              disabled={loading}
            >
              {loading ? (
                <>
                  <span className="vd-dots">
                    <span className="vd-dot" />
                    <span className="vd-dot" />
                    <span className="vd-dot" />
                  </span>
                  Генерируем промт…
                </>
              ) : (
                "→ Сгенерировать промт"
              )}
            </button>
          </div>
          {loading && <div className="vd-progress" />}
        </>
      )}
    </section>
  );
}
