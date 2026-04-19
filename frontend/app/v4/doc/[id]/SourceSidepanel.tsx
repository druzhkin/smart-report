"use client";

/** SourceSidepanel — right drawer that opens when user clicks [N] inline citation */

import { type SourceEntry } from "./DocView";

interface Props {
  open: boolean;
  source: SourceEntry | null;
  onClose: () => void;
}

export function SourceSidepanel({ open, source, onClose }: Props) {
  return (
    <>
      {/* Scrim — click outside to close */}
      {open && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 89,
            background: "transparent",
          }}
          onClick={onClose}
        />
      )}

      <div className={`vd-sidepanel${open ? " open" : ""}`}>
        <div className="vd-sidepanel-head">
          <span className="vd-sidepanel-label">Источник</span>
          <button className="vd-sidepanel-close" onClick={onClose} aria-label="Закрыть">
            ✕
          </button>
        </div>

        <div className="vd-sidepanel-body">
          {source ? (
            <>
              <div style={{
                fontFamily: "var(--vd-f-mono)",
                fontSize: 10,
                letterSpacing: "0.08em",
                textTransform: "uppercase",
                color: "var(--vd-accent)",
                fontWeight: 700,
                marginBottom: 12,
              }}>
                [{source.n}]
              </div>

              <h4>{source.title || `Источник ${source.n}`}</h4>

              <div className="vd-sidepanel-meta">
                {source.origin && <div>{source.origin}</div>}
                {source.url && (
                  <a
                    href={source.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{
                      color: "var(--vd-accent)",
                      fontSize: 11,
                      fontFamily: "var(--vd-f-mono)",
                      wordBreak: "break-all",
                    }}
                  >
                    {source.url}
                  </a>
                )}
              </div>

              <div className="vd-sidepanel-quote">
                <div style={{
                  fontFamily: "var(--vd-f-mono)",
                  fontSize: 10,
                  letterSpacing: "0.06em",
                  textTransform: "uppercase",
                  color: "var(--vd-ink-3)",
                  marginBottom: 6,
                }}>
                  Происхождение
                </div>
                <div style={{ fontSize: 13, color: "var(--vd-ink-2)" }}>
                  {source.origin || "Нет данных"}
                </div>
              </div>

              {/* TODO: no api binding — quote/excerpt not in FinalSource type, showing origin only */}
              <div style={{
                marginTop: 16,
                padding: "10px 12px",
                background: "var(--vd-paper-2)",
                fontFamily: "var(--vd-f-mono)",
                fontSize: 10,
                color: "var(--vd-ink-4)",
                letterSpacing: "0.04em",
              }}>
                Цитата недоступна: API не возвращает выдержку из источника. Откройте URL для полного текста.
              </div>
            </>
          ) : (
            <div style={{
              fontFamily: "var(--vd-f-mono)",
              fontSize: 12,
              color: "var(--vd-ink-4)",
              textAlign: "center",
              marginTop: 40,
            }}>
              Нажмите [N] в тексте, чтобы открыть источник
            </div>
          )}
        </div>
      </div>
    </>
  );
}
