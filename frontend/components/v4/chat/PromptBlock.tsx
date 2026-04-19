"use client";

/**
 * PromptBlock — assistant-side chat card rendering a ResearchPrompt.
 *
 * Layout:
 *   intro line
 *   <pre> prompt body  (mono, copy button)
 *   "почему именно так"  (collapsible, pulls prompt.reasoning)
 *   tool cards x3  (Perplexity / OpenAI DR / Claude + mode hints)
 *   Continue CTA
 */

import { useState } from "react";
import type { ResearchPrompt } from "@/lib/apiV4";
import { ChevronDown, ChevronUp, Copy, Check, ArrowRight } from "lucide-react";

const TOOLS: Array<{
  key: "perplexity" | "openai_dr" | "claude";
  label: string;
  blurb: string;
  hint: string;
}> = [
  {
    key: "perplexity",
    label: "Perplexity",
    blurb: "Широкий охват, быстрые цифры по рынку.",
    hint: "Режим: Deep Research (лупа+мозг), не Sonar и не обычный поиск.",
  },
  {
    key: "openai_dr",
    label: "OpenAI Deep Research",
    blurb: "Сравнительные разборы и финансовые модели.",
    hint: "Режим: Deep Research или o3, не стандартный GPT-4o чат.",
  },
  {
    key: "claude",
    label: "Claude",
    blurb: "Длинные рассуждения и цитирование.",
    hint: "Режим: Research toggle или включённый web search.",
  },
];

export function PromptBlock({
  prompt,
  onContinue,
}: {
  prompt: ResearchPrompt;
  onContinue: () => void;
}) {
  const [reasonOpen, setReasonOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(prompt.full_prompt);
      setCopied(true);
      setTimeout(() => setCopied(false), 1400);
    } catch {
      /* ignore */
    }
  }

  return (
    <div className="vc-reveal" style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      {/* Intro line */}
      <div
        className="vc-bubble vc-bubble-assistant"
        style={{ padding: "16px 20px" }}
      >
        <p style={{ margin: 0, fontSize: 15, lineHeight: 1.55 }}>
          Research-промт готов. Скопируйте его и запустите в Perplexity /
          OpenAI / Claude — затем загрузите полученные отчёты сюда.
        </p>
      </div>

      {/* Prompt body + copy */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: 10,
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            paddingLeft: 4,
          }}
        >
          <span className="vc-mono" style={{ fontSize: 11 }}>
            research-prompt
          </span>
          <button
            type="button"
            className="vc-btn vc-btn-ghost vc-btn-sm"
            onClick={copy}
            aria-label="Скопировать промт"
          >
            {copied ? (
              <>
                <Check size={13} strokeWidth={2} />
                <span>Скопировано</span>
              </>
            ) : (
              <>
                <Copy size={13} strokeWidth={1.75} />
                <span>Копировать</span>
              </>
            )}
          </button>
        </div>
        <pre className="vc-code" style={{ margin: 0 }}>
          {prompt.full_prompt}
        </pre>
      </div>

      {/* Reasoning collapsible */}
      {prompt.reasoning && (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <button
            type="button"
            onClick={() => setReasonOpen(!reasonOpen)}
            className="vc-btn vc-btn-ghost vc-btn-sm"
            style={{
              alignSelf: "flex-start",
              paddingLeft: 4,
              paddingRight: 4,
            }}
            aria-expanded={reasonOpen}
          >
            {reasonOpen ? (
              <ChevronUp size={13} strokeWidth={1.75} />
            ) : (
              <ChevronDown size={13} strokeWidth={1.75} />
            )}
            <span>Почему именно так</span>
          </button>
          {reasonOpen && (
            <div
              className="vc-reveal"
              style={{
                padding: "14px 18px",
                background: "var(--vc-surface-2)",
                borderRadius: 10,
                fontSize: 14,
                lineHeight: 1.6,
                color: "var(--vc-muted)",
              }}
            >
              {prompt.reasoning}
            </div>
          )}
        </div>
      )}

      {/* Tool cards */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
          gap: 10,
        }}
      >
        {TOOLS.map((t) => (
          <div
            key={t.key}
            style={{
              padding: "14px 16px",
              background: "var(--vc-surface)",
              border: "1px solid var(--vc-border)",
              borderRadius: 12,
              display: "flex",
              flexDirection: "column",
              gap: 6,
            }}
          >
            <div
              style={{
                fontSize: 13,
                fontWeight: 600,
                color: "var(--vc-text)",
              }}
            >
              {t.label}
            </div>
            <div style={{ fontSize: 12, color: "var(--vc-muted)", lineHeight: 1.5 }}>
              {t.blurb}
            </div>
            <div
              className="vc-mono"
              style={{
                fontSize: 10,
                marginTop: 6,
                lineHeight: 1.4,
                color: "var(--vc-subtle)",
              }}
            >
              {t.hint}
            </div>
          </div>
        ))}
      </div>

      {/* CTA */}
      <div>
        <button
          type="button"
          className="vc-btn vc-btn-primary"
          onClick={onContinue}
        >
          <span>Продолжить — у меня есть отчёты</span>
          <ArrowRight size={14} strokeWidth={2} />
        </button>
      </div>
    </div>
  );
}
