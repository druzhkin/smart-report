"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { getSession, generatePrompt, type ResearchPrompt, type V4Session } from "@/lib/apiV4";
import { useCost } from "@/lib/costContext";
import { LivePipeline } from "@/components/LivePipeline";
import { SectionKicker } from "@/components/v4/SectionKicker";
import { CopyButton } from "@/components/v4/CopyButton";
import { ToolMark, TOOL_DEFS } from "@/components/v4/ToolMark";
import { Icons } from "@/components/v4/Icon";
import { ProcessingOverlay } from "@/components/v4/ProcessingOverlay";

const TOOLS = ["perplexity", "openai", "claude"] as const;
const TOOL_DESC: Record<string, string> = {
  perplexity: "Широкий охват источников, быстрые срезы по рынку.",
  openai:     "Лучше всего для финансовых моделей и структурированных разборов.",
  claude:     "Сильнее в регуляторике, длинных рассуждениях и цитировании.",
};

const TOOL_MODE_HINT: Record<string, string> = {
  perplexity: "Режим: Deep Research (иконка лупы+мозга), не Sonar и не обычный поиск.",
  openai:     "Режим: Deep Research или o3, не стандартный GPT-4o чат.",
  claude:     "Режим: Research toggle под полем ввода, либо включите инструмент web search.",
};

export default function V4PromptPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = params?.id || "";
  const { setCost } = useCost();

  const [session, setSession] = useState<V4Session | null>(null);
  const [prompt, setPrompt] = useState<ResearchPrompt | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [reasonOpen, setReasonOpen] = useState(false);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    (async () => {
      try {
        const s = await getSession(id);
        if (cancelled) return;
        setSession(s);
        setCost(s.total_cost_rub);
        if (s.research_prompt) {
          setPrompt(s.research_prompt);
        } else {
          setBusy(true);
          try {
            const p = await generatePrompt(id);
            if (!cancelled) setPrompt(p);
          } finally {
            if (!cancelled) setBusy(false);
          }
        }
      } catch (e) {
        if (!cancelled) setErr(e instanceof Error ? e.message : "Не удалось загрузить");
      }
    })();
    return () => { cancelled = true; };
  }, [id]);

  async function regenerate() {
    if (busy) return;
    setBusy(true);
    setErr(null);
    try {
      const p = await generatePrompt(id);
      setPrompt(p);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Не удалось перегенерировать");
    } finally {
      setBusy(false);
    }
  }

  if (err) {
    return (
      <div className="v4-container" style={{ paddingTop: 48 }}>
        <div style={{ fontSize: 13, color: "#b91c1c" }}>{err}</div>
      </div>
    );
  }

  if (!prompt) {
    return <ProcessingOverlay stage="prompt" />;
  }

  // Determine recommended tool from prompt (map openai_dr → openai)
  const recTool = "openai"; // default; apiV4 doesn't return a recommendedTool field

  const wordCount = prompt.full_prompt.split(/\s+/).filter(Boolean).length;

  return (
    <div
      className="v4-container"
      style={{ paddingTop: 48, paddingBottom: 96, position: "relative", zIndex: 1 }}
    >
      {/* Breadcrumb */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          marginBottom: 32,
        }}
      >
        <span className="v4-mono">Исследование / Промт</span>
        <span style={{ width: 16, height: 1, background: "var(--v4-rule-strong)" }} />
        <span className="v4-mono" style={{ color: "var(--v4-ink-4)" }}>
          Загрузка отчётов →
        </span>
      </div>

      {/* Question echo */}
      <div style={{ maxWidth: 780, marginBottom: 40 }}>
        <SectionKicker number="02">Ваш вопрос</SectionKicker>
        <div
          style={{
            fontFamily: "var(--v4-f-display)",
            fontSize: 26,
            lineHeight: 1.3,
            marginTop: 12,
            color: "var(--v4-ink-2)",
          }}
        >
          «{session?.raw_question}»
        </div>
      </div>

      <LivePipeline
        events={[]}
        goal={undefined}
        mode="v4"
        phaseStatus={{ prompt: "done", external: "waiting", analyzer: "pending", synth: "pending" }}
      />

      {/* The artifact — prompt document */}
      <div style={{ marginTop: 48 }}>
        <SectionKicker>Research-промт</SectionKicker>

        <div
          className="v4-corners"
          style={{
            marginTop: 14,
            padding: 40,
            paddingTop: 32,
            position: "relative",
            background: "var(--v4-paper-2)",
            border: "1px solid var(--v4-rule-strong)",
          }}
        >
          <span className="c-tl" />
          <span className="c-br" />
          {/* Document meta */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              marginBottom: 24,
              paddingBottom: 14,
              borderBottom: "1px solid var(--v4-rule)",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
              <span className="v4-mono">Prompt · v1</span>
              <span className="v4-mono" style={{ color: "var(--v4-ink-4)" }}>·</span>
              <span
                style={{
                  fontFamily: "var(--v4-f-mono)",
                  fontVariantNumeric: "tabular-nums",
                  fontSize: 11,
                  color: "var(--v4-ink-3)",
                }}
              >
                {wordCount} слов
              </span>
            </div>
            <CopyButton
              text={prompt.full_prompt}
              variant="boxed"
              label="Копировать промт"
            />
          </div>

          {/* Prompt body */}
          <div
            style={{
              fontFamily: "var(--v4-f-display)",
              fontSize: 17,
              lineHeight: 1.65,
              color: "var(--v4-ink)",
              whiteSpace: "pre-wrap",
            }}
          >
            {prompt.full_prompt}
          </div>
        </div>

        {/* Reasoning collapsible */}
        <div style={{ marginTop: 24 }}>
          <button
            onClick={() => setReasonOpen(!reasonOpen)}
            style={{
              background: "transparent",
              border: "none",
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: 8,
              fontFamily: "var(--v4-f-body)",
              fontSize: 13,
              color: "var(--v4-ink-2)",
              padding: 0,
            }}
          >
            <span className="v4-mono">Почему именно так сформулировано</span>
            <span
              style={{
                transform: reasonOpen ? "rotate(180deg)" : "none",
                transition: "transform .2s",
                display: "inline-flex",
              }}
            >
              <Icons.chevronDown />
            </span>
          </button>
          {reasonOpen && (
            <div
              style={{
                marginTop: 14,
                padding: 20,
                background: "var(--v4-paper-2)",
                borderLeft: "2px solid var(--v4-accent)",
                fontSize: 14,
                lineHeight: 1.65,
                maxWidth: 780,
                color: "var(--v4-ink-2)",
                animation: "v4FadeIn .35s ease both",
              }}
            >
              {prompt.reasoning}
            </div>
          )}
        </div>
      </div>

      {/* Tool recommendation + next steps */}
      <div
        style={{
          marginTop: 56,
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 40,
          alignItems: "start",
        }}
      >
        <div>
          <SectionKicker>Куда отправить</SectionKicker>
          <div
            style={{
              marginTop: 14,
              display: "flex",
              flexDirection: "column",
              gap: 10,
            }}
          >
            {TOOLS.map((t) => {
              const rec = t === recTool;
              const def = TOOL_DEFS[t] || TOOL_DEFS.other;
              return (
                <div
                  key={t}
                  style={{
                    display: "grid",
                    gridTemplateColumns: "auto 1fr auto",
                    gap: 16,
                    alignItems: "center",
                    padding: "14px 16px",
                    border: rec
                      ? "1px solid var(--v4-accent)"
                      : "1px solid var(--v4-rule)",
                    background: rec ? "var(--v4-accent-wash)" : "transparent",
                  }}
                >
                  <ToolMark tool={t} size={28} />
                  <div>
                    <div style={{ fontSize: 14, fontWeight: 500, color: "var(--v4-ink)" }}>
                      {def.label}
                    </div>
                    <div
                      style={{
                        fontSize: 12,
                        color: "var(--v4-ink-3)",
                        marginTop: 2,
                      }}
                    >
                      {TOOL_DESC[t]}
                    </div>
                    <div
                      style={{
                        marginTop: 6,
                        fontFamily: "var(--v4-f-mono)",
                        fontSize: 10,
                        letterSpacing: "0.06em",
                        color: "var(--v4-accent-ink)",
                        lineHeight: 1.45,
                      }}
                    >
                      {TOOL_MODE_HINT[t]}
                    </div>
                  </div>
                  {rec ? (
                    <span className="v4-badge v4-badge-ink">Рекомендуем</span>
                  ) : (
                    <span
                      style={{ fontSize: 11, color: "var(--v4-ink-4)" }}
                    >
                      альтернатива
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        <div>
          <SectionKicker>Следующий шаг</SectionKicker>
          <ol
            style={{
              marginTop: 14,
              paddingLeft: 0,
              listStyle: "none",
              fontSize: 14,
              lineHeight: 1.65,
              color: "var(--v4-ink-2)",
            }}
          >
            {[
              "Скопируйте промт",
              `Откройте ${TOOL_DEFS[recTool]?.label || "рекомендованный инструмент"} (или 2–3 параллельно)`,
              "Вставьте, дождитесь ответа, сохраните как .md",
              "Вернитесь сюда и загрузите файлы",
            ].map((step, i) => (
              <li
                key={i}
                style={{
                  display: "grid",
                  gridTemplateColumns: "32px 1fr",
                  gap: 12,
                  paddingBottom: 14,
                  marginBottom: 14,
                  borderBottom:
                    i < 3 ? "1px solid var(--v4-rule)" : "none",
                }}
              >
                <span
                  style={{
                    fontFamily: "var(--v4-f-mono)",
                    fontVariantNumeric: "tabular-nums",
                    fontSize: 14,
                    color: "var(--v4-ink-3)",
                    fontWeight: 500,
                  }}
                >
                  0{i + 1}
                </span>
                <span>{step}</span>
              </li>
            ))}
          </ol>
        </div>
      </div>

      {/* Footer actions */}
      <div
        style={{
          marginTop: 56,
          paddingTop: 24,
          borderTop: "1px solid var(--v4-rule-emphatic)",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <button
          className="v4-btn v4-btn-secondary"
          onClick={regenerate}
          disabled={busy}
        >
          <Icons.refresh />
          {busy ? "Генерирую…" : "Перегенерировать промт"}
        </button>
        <button
          className="v4-btn v4-btn-primary"
          onClick={() => router.push(`/v4/session/${id}/upload`)}
        >
          У меня есть отчёты — продолжить
          <Icons.arrowRight />
        </button>
      </div>

      {err && (
        <div style={{ marginTop: 12, fontSize: 13, color: "#b91c1c" }}>{err}</div>
      )}
    </div>
  );
}
