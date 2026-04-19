"use client";

/**
 * /v4/chat — landing screen for a brand-new research conversation.
 *
 * Renders the empty chat canvas with a single input.  On first submit we
 * create a session via apiV4.createSession() and router.replace() to
 * /v4/chat/[id] where ChatView takes over.  Also handles ?q= prefill so
 * links like /v4/chat?q=… launch with the question pre-entered.
 */

import { useState, useEffect, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { createSession, STUB_ENABLED } from "@/lib/apiV4";
import { CostProvider } from "@/lib/costContext";
import { StatusBar } from "@/components/v4/chat/StatusBar";
import { Composer } from "@/components/v4/chat/Composer";

const EXAMPLES = [
  "Что определяет успех девелопера в бизнес-сегменте Москвы — бренд, скорость или продукт?",
  "Как облачные БД изменят enterprise data stack в следующие 3 года?",
  "Что движет оттоком ML-инженеров из бигтеха в стартапы в 2025?",
];

function ChatLanding() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [prefill, setPrefill] = useState<string>("");

  useEffect(() => {
    const q = searchParams?.get("q") || "";
    if (q) setPrefill(q);
  }, [searchParams]);

  async function submit(text: string) {
    if (busy || !text.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const res = await createSession(text.trim());
      router.replace(`/v4/chat/${res.session_id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось создать сессию");
      setBusy(false);
    }
  }

  return (
    <div className="v4-chat-host v4-chat">
      <StatusBar
        stage={{ step: 1, total: 5, label: "Новое исследование" }}
        running={busy}
      />

      <div
        style={{
          flex: 1,
          overflowY: "auto",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          padding: "48px 24px",
        }}
      >
        <div
          className="vc-reveal"
          style={{
            maxWidth: 620,
            width: "100%",
            display: "flex",
            flexDirection: "column",
            gap: 24,
          }}
        >
          <div>
            <div className="vc-mono" style={{ fontSize: 11, marginBottom: 12 }}>
              smart report · мета-анализ исследований
            </div>
            <h1 className="vc-h1" style={{ margin: 0 }}>
              Задайте исследовательский вопрос.
            </h1>
            <p
              className="vc-meta"
              style={{ marginTop: 12, maxWidth: 540 }}
            >
              Prompt Master соберёт research-промт, вы запустите его в Perplexity /
              OpenAI / Claude, загрузите отчёты сюда — и получите синтез поверх
              трёх поисков.
            </p>
          </div>

          {error && (
            <div
              style={{
                padding: "12px 16px",
                background: "var(--vc-danger-w)",
                border: "1px solid rgba(185,28,28,0.25)",
                borderRadius: 12,
                color: "var(--vc-danger)",
                fontSize: 13,
              }}
            >
              {error}
            </div>
          )}

          <Composer
            key={prefill /* remount when prefill arrives */}
            placeholder="Например: что определяет успех девелопера в бизнес-сегменте Москвы?"
            onSubmit={submit}
            autoFocus
            busy={busy}
            helper="Cmd/Ctrl + Enter — запустить"
          />

          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: 6,
              paddingTop: 8,
            }}
          >
            <div className="vc-mono" style={{ fontSize: 11 }}>
              примеры
            </div>
            {EXAMPLES.map((ex) => (
              <button
                key={ex}
                type="button"
                onClick={() => submit(ex)}
                disabled={busy}
                style={{
                  textAlign: "left",
                  padding: "10px 14px",
                  background: "var(--vc-surface)",
                  border: "1px solid var(--vc-border)",
                  borderRadius: 10,
                  color: "var(--vc-muted)",
                  fontFamily: "inherit",
                  fontSize: 13,
                  lineHeight: 1.45,
                  cursor: busy ? "not-allowed" : "pointer",
                  transition: "border-color 140ms ease, color 140ms ease, background 140ms ease",
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.borderColor = "var(--vc-border-s)";
                  e.currentTarget.style.color = "var(--vc-text)";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.borderColor = "var(--vc-border)";
                  e.currentTarget.style.color = "var(--vc-muted)";
                }}
              >
                {ex}
              </button>
            ))}
          </div>

          {STUB_ENABLED && (
            <div className="vc-mono" style={{ fontSize: 10 }}>
              stub mode · данные подделаны
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function V4ChatLandingPage() {
  return (
    <CostProvider>
      <Suspense
        fallback={
          <div
            className="v4-chat-host v4-chat"
            style={{ alignItems: "center", justifyContent: "center" }}
          >
            <div className="vc-meta">Загружаю…</div>
          </div>
        }
      >
        <ChatLanding />
      </Suspense>
    </CostProvider>
  );
}
