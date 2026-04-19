"use client";

/**
 * /v4/doc — entry point for the Swiss document UI.
 * Creates a session and navigates to /v4/doc/[id].
 * Accepts ?q= query param (e.g. from /v4/new redirect).
 */

import { useState, useEffect, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { createSession } from "@/lib/apiV4";
import { ModelPicker } from "@/components/ModelPicker";

function DocEntryInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const q = searchParams.get("q");
    if (q) setQuestion(q);
  }, [searchParams]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const q = question.trim();
    if (!q) return;
    setLoading(true);
    setError(null);
    try {
      const { session_id } = await createSession(q);
      router.push(`/v4/doc/${session_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка создания сессии");
      setLoading(false);
    }
  }

  return (
    <div className="v4-doc" style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div style={{ maxWidth: 600, width: "100%", padding: "0 32px" }}>
        <div className="vd-section-kicker" style={{ marginBottom: 24 }}>
          <span className="vd-kicker-num">01</span>
          Smart Report V.IV
        </div>
        <h1 className="vd-h1" style={{ fontSize: 28, marginBottom: 20 }}>Новое исследование</h1>
        <form onSubmit={handleSubmit}>
          <textarea
            className="vd-question-field"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Введите вопрос для исследования…"
            rows={5}
            disabled={loading}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                handleSubmit(e as unknown as React.FormEvent);
              }
            }}
          />
          {error && (
            <div style={{ color: "var(--vd-bad)", fontFamily: "var(--vd-f-mono)", fontSize: 12, marginTop: 8 }}>
              {error}
            </div>
          )}
          <div className="vd-actions">
            <ModelPicker />
            <button
              type="submit"
              className="vd-btn-primary"
              disabled={loading || !question.trim()}
            >
              {loading ? (
                <>
                  <span className="vd-dots">
                    <span className="vd-dot" />
                    <span className="vd-dot" />
                    <span className="vd-dot" />
                  </span>
                  Создаём…
                </>
              ) : (
                "→ Начать исследование"
              )}
            </button>
            <span style={{ fontFamily: "var(--vd-f-mono)", fontSize: 10, color: "var(--vd-ink-4)", letterSpacing: "0.06em" }}>
              Ctrl+Enter
            </span>
          </div>
        </form>
      </div>
    </div>
  );
}

export default function DocEntryPage() {
  return (
    <Suspense fallback={
      <div className="v4-doc" style={{ display: "flex", alignItems: "center", justifyContent: "center", minHeight: "100vh" }}>
        <div className="vd-dots">
          <div className="vd-dot" />
          <div className="vd-dot" />
          <div className="vd-dot" />
        </div>
      </div>
    }>
      <DocEntryInner />
    </Suspense>
  );
}
