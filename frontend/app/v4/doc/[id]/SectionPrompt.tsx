"use client";

/** Section 02 — PROMPT: shows the generated research prompt */

import { useState } from "react";
import { type V4Session } from "@/lib/apiV4";

interface Props {
  session: V4Session;
}

const TOOL_RECS = [
  { id: "claude",       label: "Claude Research",    score: 92, top: true },
  { id: "perplexity",   label: "Perplexity DR",      score: 78, top: false },
  { id: "openai_dr",    label: "OpenAI DR",          score: 74, top: false },
];

export function SectionPrompt({ session }: Props) {
  const prompt = session.research_prompt;
  const [copied, setCopied] = useState(false);

  if (!prompt) return null;

  const fullText = prompt.full_prompt;
  const wordCount = fullText.trim().split(/\s+/).length;

  function copy() {
    try { navigator.clipboard.writeText(fullText); } catch {}
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  }

  return (
    <section className="vd-section">
      <div className="vd-section-kicker">
        <span className="vd-kicker-num">02</span>
        Research-промт
      </div>
      <h2 className="vd-h2">Промт для внешнего исследования</h2>

      {/* Metadata row */}
      <div style={{
        fontFamily: "var(--vd-f-mono)",
        fontSize: 10,
        color: "var(--vd-ink-3)",
        letterSpacing: "0.06em",
        marginBottom: 16,
        display: "flex",
        gap: 12,
        alignItems: "center",
      }}>
        <span>{wordCount.toLocaleString("ru-RU")} слов</span>
        <span>·</span>
        <span>готов к копированию</span>
      </div>

      {/* Tool recommendations */}
      <div style={{
        background: "var(--vd-paper-2)",
        border: "1px solid var(--vd-rule)",
        padding: "14px 16px",
        marginBottom: 20,
      }}>
        <div style={{
          fontFamily: "var(--vd-f-mono)",
          fontSize: 10,
          color: "var(--vd-ink-3)",
          letterSpacing: "0.06em",
          textTransform: "uppercase",
          marginBottom: 10,
        }}>
          Рекомендуемые инструменты
        </div>
        <div className="vd-tool-rec">
          {TOOL_RECS.map((t) => (
            <span key={t.id} className={`vd-tool-chip${t.top ? " top" : ""}`}>
              {t.top && <span>★</span>}
              {t.label}
              <span style={{ fontFamily: "var(--vd-f-mono)", fontSize: 10, opacity: 0.7 }}>{t.score}</span>
            </span>
          ))}
        </div>
        {prompt.reasoning && (
          <div style={{ fontSize: 12, color: "var(--vd-ink-2)", lineHeight: 1.5 }}>
            {prompt.reasoning}
          </div>
        )}
      </div>

      {/* Full prompt box */}
      <div className="vd-prompt-box" style={{ position: "relative" }}>
        <div className="vd-prompt-text">{fullText}</div>
      </div>

      {/* Tips */}
      {prompt.tips_for_search && (
        <div style={{
          marginTop: 16,
          padding: "12px 14px",
          background: "var(--vd-paper-2)",
          borderLeft: "3px solid var(--vd-rule)",
          fontSize: 12,
          color: "var(--vd-ink-3)",
          lineHeight: 1.55,
        }}>
          <div style={{
            fontFamily: "var(--vd-f-mono)",
            fontSize: 10,
            letterSpacing: "0.06em",
            textTransform: "uppercase",
            marginBottom: 6,
            color: "var(--vd-ink-4)",
          }}>
            Подсказка
          </div>
          {prompt.tips_for_search}
        </div>
      )}

      {/* Expected structure */}
      {prompt.expected_structure?.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <div style={{
            fontFamily: "var(--vd-f-mono)",
            fontSize: 10,
            letterSpacing: "0.06em",
            textTransform: "uppercase",
            color: "var(--vd-ink-3)",
            marginBottom: 8,
          }}>
            Ожидаемая структура ответа
          </div>
          <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
            {prompt.expected_structure.map((s, i) => (
              <li key={i} style={{
                fontSize: 13,
                lineHeight: 1.6,
                color: "var(--vd-ink-2)",
                paddingLeft: 18,
                position: "relative",
                marginBottom: 4,
              }}>
                <span style={{
                  position: "absolute",
                  left: 0,
                  fontFamily: "var(--vd-f-mono)",
                  fontSize: 10,
                  color: "var(--vd-accent)",
                  fontWeight: 700,
                }}>
                  {String(i + 1).padStart(2, "0")}
                </span>
                {s}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Copy action */}
      <div className="vd-actions" style={{ marginTop: 20 }}>
        <button className="vd-copy-btn" onClick={copy}>
          {copied ? "✓ Скопировано" : "Скопировать промт"}
        </button>
      </div>
    </section>
  );
}
