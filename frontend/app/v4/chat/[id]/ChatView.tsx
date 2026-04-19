"use client";

/**
 * ChatView — single-route full-chat UI for the v4 research meta-analysis.
 *
 * State → messages mapping (derived from V4Session server-side state, NOT
 * from a local turn counter — users can arrive mid-flow):
 *
 *   1  raw_question                             → user bubble
 *   2  research_prompt (prompt_ready)           → assistant PromptBlock
 *   3  stage 3 input                            → UploadComposer (reports)
 *   4  source_reports (reports_uploaded)        → user "N reports uploaded"
 *   5  thinking                                 → Thinking (analyzing)
 *   6  analysis (analyzed)                      → assistant CritiqueBlock
 *   7  stage 7 input                            → UploadComposer (followup)
 *   8  followup_reports + thinking              → Thinking (synthesizing)
 *   9  final_report (synthesized)               → assistant FinalReportBlock
 *
 * All side-effects go through lib/apiV4 — no new endpoints added.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  getSession,
  generatePrompt,
  uploadReports,
  analyze,
  uploadFollowup,
  synthesize,
  createSession,
  STUB_ENABLED,
  type V4Session,
} from "@/lib/apiV4";
import { useCost } from "@/lib/costContext";
import { StatusBar, type StatusStage } from "@/components/v4/chat/StatusBar";
import { MessageBubble, Thinking } from "@/components/v4/chat/MessageBubble";
import { Composer } from "@/components/v4/chat/Composer";
import { UploadComposer } from "@/components/v4/chat/UploadComposer";
import { PromptBlock } from "@/components/v4/chat/PromptBlock";
import { CritiqueBlock } from "@/components/v4/chat/CritiqueBlock";
import { FinalReportBlock } from "@/components/v4/chat/FinalReportBlock";

type Busy = "prompt" | "analyze" | "synthesize" | null;

function stageFromSession(s: V4Session | null, busy: Busy): StatusStage {
  if (!s) return { step: 1, total: 5, label: "Вопрос" };
  if (busy === "prompt") return { step: 1, total: 5, label: "Промт готовится" };
  if (busy === "analyze") return { step: 3, total: 5, label: "Анализ" };
  if (busy === "synthesize") return { step: 4, total: 5, label: "Синтез" };
  if (s.final_report) return { step: 5, total: 5, label: "Финал" };
  if (s.analysis) return { step: 4, total: 5, label: "Добор или синтез" };
  if (s.source_reports.length > 0) return { step: 3, total: 5, label: "Анализ" };
  if (s.research_prompt) return { step: 2, total: 5, label: "Загрузка отчётов" };
  return { step: 1, total: 5, label: "Вопрос" };
}

export function ChatView({ sessionId }: { sessionId: string }) {
  const router = useRouter();
  const { setCost } = useCost();

  const [session, setSession] = useState<V4Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [busy, setBusy] = useState<Busy>(null);
  const [thinkingLabel, setThinkingLabel] = useState<string>("");

  // When user explicitly skips followup-upload step, remember it so we don't
  // keep showing the upload composer after returning.
  const [skippedFollowup, setSkippedFollowup] = useState(false);

  const scrollRef = useRef<HTMLDivElement>(null);

  // ---------- load session on mount / id change ---------------------
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getSession(sessionId)
      .then((s) => {
        if (cancelled) return;
        setSession(s);
        setCost(s.total_cost_rub);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Не удалось загрузить сессию");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId, setCost]);

  // ---------- auto-generate prompt on first mount ------------------
  const autoPromptStarted = useRef(false);
  useEffect(() => {
    if (!session) return;
    if (autoPromptStarted.current) return;
    if (session.research_prompt) return;
    if (!session.raw_question) return;
    autoPromptStarted.current = true;
    runGeneratePrompt();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session?.session_id, session?.research_prompt, session?.raw_question]);

  // ---------- auto-scroll when content changes ---------------------
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    // Smooth scroll to bottom
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [session?.status, busy, thinkingLabel, skippedFollowup]);

  // ---------- mutations --------------------------------------------
  const runGeneratePrompt = useCallback(async () => {
    setBusy("prompt");
    setThinkingLabel("Собираю research-промт…");
    setError(null);
    try {
      await generatePrompt(sessionId);
      const fresh = await getSession(sessionId);
      setSession(fresh);
      setCost(fresh.total_cost_rub);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось создать промт");
    } finally {
      setBusy(null);
      setThinkingLabel("");
    }
  }, [sessionId, setCost]);

  const runUploadReports = useCallback(
    async (files: File[]) => {
      setError(null);
      try {
        await uploadReports(sessionId, files);
        const afterUpload = await getSession(sessionId);
        setSession(afterUpload);
        setCost(afterUpload.total_cost_rub);
        // Immediately kick off analysis — classic chat flow
        setBusy("analyze");
        setThinkingLabel("Читаю отчёты, ищу противоречия…");
        await analyze(sessionId);
        const afterAnalyze = await getSession(sessionId);
        setSession(afterAnalyze);
        setCost(afterAnalyze.total_cost_rub);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Не удалось проанализировать");
      } finally {
        setBusy(null);
        setThinkingLabel("");
      }
    },
    [sessionId, setCost]
  );

  const runFollowupAndSynth = useCallback(
    async (files: File[] | null) => {
      setError(null);
      try {
        if (files && files.length > 0) {
          await uploadFollowup(sessionId, files);
          const afterUp = await getSession(sessionId);
          setSession(afterUp);
          setCost(afterUp.total_cost_rub);
        } else {
          setSkippedFollowup(true);
        }
        setBusy("synthesize");
        setThinkingLabel("Собираю финальный синтез…");
        await synthesize(sessionId);
        const afterSyn = await getSession(sessionId);
        setSession(afterSyn);
        setCost(afterSyn.total_cost_rub);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Не удалось собрать финал");
      } finally {
        setBusy(null);
        setThinkingLabel("");
      }
    },
    [sessionId, setCost]
  );

  const newResearch = useCallback(() => {
    router.push("/v4/chat");
  }, [router]);

  const retry = useCallback(async () => {
    // Smart retry — rerun the mutation matching the last state
    setError(null);
    if (!session) return;
    if (!session.research_prompt) return runGeneratePrompt();
    if (session.research_prompt && !session.analysis && session.source_reports.length > 0) {
      // analysis phase
      setBusy("analyze");
      setThinkingLabel("Читаю отчёты, ищу противоречия…");
      try {
        await analyze(sessionId);
        const fresh = await getSession(sessionId);
        setSession(fresh);
        setCost(fresh.total_cost_rub);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Не удалось проанализировать");
      } finally {
        setBusy(null);
        setThinkingLabel("");
      }
    }
  }, [session, runGeneratePrompt, sessionId, setCost]);

  // ---------- render ------------------------------------------------
  const stage = useMemo(() => stageFromSession(session, busy), [session, busy]);

  // What composer is shown at the bottom right now?
  const bottomSlot = useMemo(() => {
    if (!session) return "none";
    if (busy) return "none"; // hide composer during thinking
    if (session.final_report) return "done";
    if (session.analysis && !skippedFollowup && session.followup_reports.length === 0)
      return "upload-followup";
    if (session.research_prompt && session.source_reports.length === 0) return "upload-reports";
    if (!session.research_prompt && !session.raw_question) return "text";
    return "none";
  }, [session, busy, skippedFollowup]);

  return (
    <div className="v4-chat-host v4-chat">
      <StatusBar
        stage={stage}
        running={busy !== null}
        onNewResearch={newResearch}
      />

      {/* Scroll region */}
      <div
        ref={scrollRef}
        style={{
          flex: 1,
          overflowY: "auto",
          overflowX: "hidden",
          paddingBottom: 16,
        }}
      >
        <div
          style={{
            maxWidth: 760,
            margin: "0 auto",
            padding: "40px 24px 32px",
            display: "flex",
            flexDirection: "column",
            gap: 40,
          }}
        >
          {loading && !session && (
            <div className="vc-meta" style={{ textAlign: "center" }}>
              Загружаю сессию…
            </div>
          )}

          {error && (
            <div
              className="vc-reveal"
              style={{
                padding: "12px 16px",
                background: "var(--vc-danger-w)",
                border: "1px solid rgba(185,28,28,0.25)",
                borderRadius: 12,
                color: "var(--vc-danger)",
                fontSize: 13,
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 12,
              }}
            >
              <span>{error}</span>
              <button
                type="button"
                className="vc-btn vc-btn-ghost vc-btn-sm"
                onClick={retry}
                style={{ color: "var(--vc-danger)" }}
              >
                Повторить
              </button>
            </div>
          )}

          {/* STUB banner */}
          {STUB_ENABLED && (
            <div className="vc-mono" style={{ textAlign: "center", fontSize: 10 }}>
              stub mode
            </div>
          )}

          {/* 1. user question */}
          {session?.raw_question && (
            <MessageBubble role="user">{session.raw_question}</MessageBubble>
          )}

          {/* 2. assistant prompt */}
          {session?.research_prompt && (
            <PromptBlock
              prompt={session.research_prompt}
              onContinue={() => {
                // no-op: the UploadComposer is already the active bottom slot;
                // scroll it into view.
                scrollRef.current?.scrollTo({
                  top: scrollRef.current.scrollHeight,
                  behavior: "smooth",
                });
              }}
            />
          )}

          {/* Thinking while generating prompt */}
          {busy === "prompt" && !session?.research_prompt && (
            <Thinking label={thinkingLabel || "Готовлю промт…"} />
          )}

          {/* 4. user: reports uploaded */}
          {session?.source_reports && session.source_reports.length > 0 && (
            <MessageBubble role="user">
              Загрузил{" "}
              {session.source_reports.length}{" "}
              {pluralRu(session.source_reports.length, ["отчёт", "отчёта", "отчётов"])}:{" "}
              {session.source_reports.map((r) => r.filename).join(", ")}
            </MessageBubble>
          )}

          {/* 5. Thinking: analyzing */}
          {busy === "analyze" && <Thinking label={thinkingLabel || "Анализирую…"} />}

          {/* 6. assistant critique */}
          {session?.analysis && (
            <CritiqueBlock
              analysis={session.analysis}
              sourceCount={session.source_reports.length}
              onContinue={() => {
                scrollRef.current?.scrollTo({
                  top: scrollRef.current.scrollHeight,
                  behavior: "smooth",
                });
              }}
            />
          )}

          {/* 7. user: uploaded followup OR skipped followup */}
          {session?.followup_reports && session.followup_reports.length > 0 && (
            <MessageBubble role="user">
              Загрузил {session.followup_reports.length}{" "}
              {pluralRu(session.followup_reports.length, [
                "доборный отчёт",
                "доборных отчёта",
                "доборных отчётов",
              ])}
              .
            </MessageBubble>
          )}

          {skippedFollowup &&
            session?.analysis &&
            session.followup_reports.length === 0 &&
            !session.final_report &&
            busy !== "synthesize" && (
              <MessageBubble role="user">
                Собрать синтез без добора.
              </MessageBubble>
            )}

          {/* 8. Thinking: synthesizing */}
          {busy === "synthesize" && <Thinking label={thinkingLabel || "Собираю синтез…"} />}

          {/* 9. assistant final report */}
          {session?.final_report && (
            <FinalReportBlock
              report={session.final_report}
              onNewResearch={newResearch}
            />
          )}
        </div>
      </div>

      {/* Composer area */}
      {bottomSlot !== "none" && (
        <div
          style={{
            flexShrink: 0,
            borderTop: "1px solid var(--vc-border)",
            background: "var(--vc-bg)",
          }}
        >
          <div style={{ maxWidth: 760, margin: "0 auto", padding: "16px 24px 20px" }}>
            {bottomSlot === "text" && (
              <Composer
                placeholder="Задайте вопрос…"
                autoFocus
                helper="Cmd/Ctrl + Enter — отправить"
                onSubmit={async (text) => {
                  // Edge-case: session was created empty (created directly by
                  // /v4/chat/[id] without a raw_question).  Make a new session.
                  try {
                    const res = await createSession(text);
                    router.replace(`/v4/chat/${res.session_id}`);
                  } catch (e) {
                    setError(e instanceof Error ? e.message : "Не удалось создать сессию");
                  }
                }}
              />
            )}
            {bottomSlot === "upload-reports" && (
              <UploadComposer
                placeholder="Перетащите отчёты от Perplexity / OpenAI / Claude"
                onSubmit={runUploadReports}
                busy={busy !== null}
              />
            )}
            {bottomSlot === "upload-followup" && (
              <UploadComposer
                placeholder="Если запустили followup — загрузите файл ответа"
                submitLabel="Отправить и собрать синтез"
                onSubmit={(files) => runFollowupAndSynth(files)}
                allowSkip
                onSkip={() => runFollowupAndSynth(null)}
                skipLabel="Пропустить — синтез без добора"
                busy={busy !== null}
              />
            )}
            {bottomSlot === "done" && (
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: 12,
                }}
              >
                <span className="vc-meta">Отчёт готов. Можно собрать ещё одно исследование.</span>
                <button
                  type="button"
                  className="vc-btn vc-btn-primary vc-btn-sm"
                  onClick={newResearch}
                >
                  Новое исследование
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function pluralRu(n: number, forms: [string, string, string]): string {
  const m10 = n % 10;
  const m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return forms[0];
  if (m10 >= 2 && m10 <= 4 && (m100 < 10 || m100 >= 20)) return forms[1];
  return forms[2];
}
