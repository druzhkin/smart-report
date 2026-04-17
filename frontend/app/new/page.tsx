"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  intakeStart,
  intakeAnswer,
  intakeConfirm,
  startResearch,
  type IntakeTier,
} from "@/lib/api";
import { MessageSquare, Send, ArrowRight, Check, Play } from "lucide-react";

type Phase = "idle" | "dialog" | "proposal" | "launching";

type ChatMsg = { role: "assistant" | "user"; text: string };

type Proposal = {
  tier: IntakeTier;
  rationale: string;
  enriched_goal: string;
};

const TIERS: {
  id: IntakeTier;
  label: string;
  time: string;
  price: string;
}[] = [
  { id: "quick_take", label: "Быстрый ответ", time: "~2 мин", price: "~50 ₽" },
  {
    id: "investment_brief",
    label: "Аналитическая записка",
    time: "~5–8 мин",
    price: "~150 ₽",
  },
  {
    id: "strategy_note",
    label: "Стратегическая нота",
    time: "~12–15 мин",
    price: "~500 ₽",
  },
  {
    id: "full_research",
    label: "Полное исследование",
    time: "20–40 мин",
    price: "~1 200 ₽",
  },
];

const EXAMPLES = [
  "За что реально готовы платить покупатели квартир бизнес и премиум класса в Москве",
  "Как сделать сильный глубокий аналитический движок",
  "Как ИИ изменит персональную медицину в ближайшие 5 лет",
];

export default function NewRequestPage() {
  const router = useRouter();

  const [phase, setPhase] = useState<Phase>("idle");
  const [goal, setGoal] = useState("");
  const [sessionId, setSessionId] = useState("");
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [turn, setTurn] = useState(0);
  const [answer, setAnswer] = useState("");
  const [typing, setTyping] = useState(false);
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [selectedTier, setSelectedTier] = useState<IntakeTier>("investment_brief");
  const [enrichedGoal, setEnrichedGoal] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [fallback, setFallback] = useState(false);
  const [fallbackDepth, setFallbackDepth] = useState<
    "light" | "standard" | "deep" | "exhaustive"
  >("standard");

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const answerRef = useRef<HTMLInputElement>(null as any);

  async function startDialog() {
    const g = goal.trim();
    if (!g) return;
    setErr(null);
    setTyping(true);
    try {
      const res = await intakeStart(g);
      if (!res) {
        setFallback(true);
        setTyping(false);
        return;
      }
      setSessionId(res.session_id);
      setTurn(res.turn);
      setMessages([{ role: "assistant", text: res.question }]);
      setPhase("dialog");
    } catch (e: unknown) {
      setErr((e as Error)?.message || "Ошибка при запуске диалога");
      setFallback(true);
    } finally {
      setTyping(false);
    }
  }

  async function sendAnswer() {
    const a = answer.trim();
    if (!a || typing) return;
    setMessages((m) => [...m, { role: "user", text: a }]);
    setAnswer("");
    setTyping(true);
    setErr(null);
    try {
      const res = await intakeAnswer(sessionId, a);
      setTurn(res.turn);
      if (res.mode === "question") {
        setMessages((m) => [...m, { role: "assistant", text: res.question }]);
      } else {
        setProposal(res.proposal);
        setSelectedTier(res.proposal.tier);
        setEnrichedGoal(res.proposal.enriched_goal);
        setPhase("proposal");
      }
    } catch (e: unknown) {
      setErr((e as Error)?.message || "Ошибка при отправке ответа");
    } finally {
      setTyping(false);
      setTimeout(() => answerRef.current?.focus(), 50);
    }
  }

  async function confirm() {
    setPhase("launching");
    setErr(null);
    try {
      const res = await intakeConfirm(
        sessionId,
        selectedTier,
        enrichedGoal.trim() || undefined
      );
      router.push(`/report/${res.id}`);
    } catch (e: unknown) {
      setErr((e as Error)?.message || "Ошибка при запуске");
      setPhase("proposal");
    }
  }

  async function skip() {
    const g = goal.trim();
    if (!g) return;
    setPhase("launching");
    setErr(null);
    try {
      const { id } = await startResearch(g, "standard");
      router.push(`/report/${id}`);
    } catch (e: unknown) {
      setErr((e as Error)?.message || "Не удалось запустить");
      setPhase("idle");
    }
  }

  async function fallbackSubmit() {
    const g = goal.trim();
    if (!g) return;
    setPhase("launching");
    setErr(null);
    try {
      const { id } = await startResearch(g, fallbackDepth);
      router.push(`/report/${id}`);
    } catch (e: unknown) {
      setErr((e as Error)?.message || "Не удалось запустить");
      setPhase("idle");
    }
  }

  function onAnswerKey(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendAnswer();
    }
  }

  function onGoalKey(e: React.KeyboardEvent) {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") startDialog();
  }

  if (phase === "launching") {
    return (
      <div className="max-w-3xl mx-auto">
        <div
          className="card flex items-center justify-center"
          style={{ padding: "3rem", minHeight: "200px" }}
        >
          <div className="text-center space-y-3">
            <TypingDots />
            <p className="text-sm muted">Запускаю исследование…</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto space-y-8">
      <section
        className="card relative overflow-hidden"
        style={{ padding: "2rem", boxShadow: "0 8px 30px rgb(0 0 0 / 0.04)" }}
      >
        <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-blue-400 via-indigo-500 to-purple-400 opacity-40" />

        {phase === "idle" && (
          <IdlePhase
            goal={goal}
            setGoal={setGoal}
            onGoalKey={onGoalKey}
            typing={typing}
            fallback={fallback}
            fallbackDepth={fallbackDepth}
            setFallbackDepth={setFallbackDepth}
            err={err}
            onStartDialog={startDialog}
            onSkip={skip}
            onFallbackSubmit={fallbackSubmit}
          />
        )}

        {phase === "dialog" && (
          <DialogPhase
            messages={messages}
            turn={turn}
            answer={answer}
            setAnswer={setAnswer}
            typing={typing}
            err={err}
            answerRef={answerRef}
            onSend={sendAnswer}
            onAnswerKey={onAnswerKey}
          />
        )}

        {phase === "proposal" && proposal && (
          <ProposalPhase
            proposal={proposal}
            selectedTier={selectedTier}
            setSelectedTier={setSelectedTier}
            enrichedGoal={enrichedGoal}
            setEnrichedGoal={setEnrichedGoal}
            err={err}
            onConfirm={confirm}
          />
        )}
      </section>
    </div>
  );
}

function TypingDots() {
  return (
    <span className="inline-flex items-center gap-1">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="w-2 h-2 rounded-full"
          style={{
            background: "var(--muted)",
            animation: `bounce 1.2s ease-in-out ${i * 0.2}s infinite`,
          }}
        />
      ))}
      <style>{`
        @keyframes bounce {
          0%, 80%, 100% { transform: translateY(0); opacity: 0.4; }
          40% { transform: translateY(-6px); opacity: 1; }
        }
      `}</style>
    </span>
  );
}

type IdlePhaseProps = {
  goal: string;
  setGoal: (v: string) => void;
  onGoalKey: (e: React.KeyboardEvent) => void;
  typing: boolean;
  fallback: boolean;
  fallbackDepth: "light" | "standard" | "deep" | "exhaustive";
  setFallbackDepth: (d: "light" | "standard" | "deep" | "exhaustive") => void;
  err: string | null;
  onStartDialog: () => void;
  onSkip: () => void;
  onFallbackSubmit: () => void;
};

const FALLBACK_DEPTHS: {
  id: "light" | "standard" | "deep" | "exhaustive";
  label: string;
  hint: string;
}[] = [
  { id: "light", label: "Light", hint: "Быстрое резюме • ~2 мин" },
  { id: "standard", label: "Standard", hint: "Широкие источники • ~5 мин" },
  { id: "deep", label: "Deep", hint: "Академический фокус • ~12 мин" },
  { id: "exhaustive", label: "Exhaustive", hint: "Полный синтез • 20+ мин" },
];

function IdlePhase({
  goal,
  setGoal,
  onGoalKey,
  typing,
  fallback,
  fallbackDepth,
  setFallbackDepth,
  err,
  onStartDialog,
  onSkip,
  onFallbackSubmit,
}: IdlePhaseProps) {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="font-serif text-2xl font-semibold tracking-tight mb-1">
          Новое исследование
        </h2>
        <p className="text-sm muted">
          Сформулируй цель — бекенд задаст 2–4 уточняющих вопроса и предложит
          оптимальный уровень анализа.
        </p>
      </div>

      <div className="relative">
        <label htmlFor="query" className="sr-only">
          Цель исследования
        </label>
        <textarea
          id="query"
          rows={4}
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          onKeyDown={onGoalKey}
          placeholder="Например: как ИИ изменит персональную медицину в ближайшие 5 лет, включая регуляторные барьеры"
          className="pb-10 resize-none"
          style={{ fontSize: "15px" }}
        />
        <div className="absolute bottom-3 right-3 flex items-center gap-3 text-xs muted pointer-events-none select-none">
          <span>{goal.length} / 500</span>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        {EXAMPLES.map((s) => (
          <button
            key={s}
            type="button"
            className="btn text-xs"
            onClick={() => setGoal(s)}
            title={s}
          >
            {s.length > 60 ? s.slice(0, 60) + "…" : s}
          </button>
        ))}
      </div>

      {fallback && (
        <div className="space-y-3">
          <p className="text-sm muted">
            Диалог недоступен — выбери глубину вручную:
          </p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {FALLBACK_DEPTHS.map((d) => {
              const active = fallbackDepth === d.id;
              return (
                <button
                  key={d.id}
                  type="button"
                  onClick={() => setFallbackDepth(d.id)}
                  className="relative text-left rounded-lg p-4 transition-all active:scale-[0.98]"
                  style={{
                    background: "var(--card)",
                    border: active
                      ? "1px solid var(--fg)"
                      : "1px solid var(--border)",
                    boxShadow: active
                      ? "0 0 0 1px var(--fg)"
                      : "0 1px 2px rgb(0 0 0 / 0.04)",
                  }}
                >
                  <div className="text-sm font-medium">{d.label}</div>
                  <div className="mt-1 text-xs muted">{d.hint}</div>
                  {active && (
                    <Check
                      size={16}
                      className="absolute top-3 right-3"
                      style={{ color: "var(--fg)" }}
                    />
                  )}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {err && <div className="text-sm text-red-600">{err}</div>}

      <div
        className="flex items-center justify-between pt-4 flex-wrap gap-3"
        style={{ borderTop: "1px solid var(--border)" }}
      >
        <button
          type="button"
          className="btn text-sm"
          onClick={onSkip}
          disabled={!goal.trim() || typing}
        >
          <ArrowRight size={14} />
          Запустить без диалога
        </button>

        {fallback ? (
          <button
            className="btn btn-primary"
            onClick={onFallbackSubmit}
            disabled={!goal.trim() || typing}
            style={{ padding: "10px 20px" }}
          >
            <Play size={14} />
            Запустить
          </button>
        ) : (
          <button
            className="btn btn-primary"
            onClick={onStartDialog}
            disabled={!goal.trim() || typing}
            style={{ padding: "10px 20px" }}
          >
            <MessageSquare size={14} />
            {typing ? "Загружаю…" : "Обсудить задачу"}
          </button>
        )}
      </div>
    </div>
  );
}

type DialogPhaseProps = {
  messages: ChatMsg[];
  turn: number;
  answer: string;
  setAnswer: (v: string) => void;
  typing: boolean;
  err: string | null;
  answerRef: React.RefObject<HTMLInputElement>;
  onSend: () => void;
  onAnswerKey: (e: React.KeyboardEvent) => void;
};

function DialogPhase({
  messages,
  turn,
  answer,
  setAnswer,
  typing,
  err,
  answerRef,
  onSend,
  onAnswerKey,
}: DialogPhaseProps) {
  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h2 className="font-serif text-xl font-semibold tracking-tight">
          Уточнение задачи
        </h2>
        <span className="text-xs muted px-2 py-1 rounded-full" style={{ border: "1px solid var(--border)" }}>
          Вопрос {turn} из 4
        </span>
      </div>

      <div className="space-y-3" style={{ minHeight: "160px" }}>
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className="max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed"
              style={
                msg.role === "assistant"
                  ? {
                      background: "color-mix(in srgb, var(--border) 40%, var(--bg) 60%)",
                      color: "var(--fg)",
                      borderBottomLeftRadius: "4px",
                    }
                  : {
                      background: "var(--accent-soft)",
                      color: "var(--fg)",
                      border: "1px solid color-mix(in srgb, var(--accent) 30%, transparent)",
                      borderBottomRightRadius: "4px",
                    }
              }
            >
              {msg.text}
            </div>
          </div>
        ))}

        {typing && (
          <div className="flex justify-start">
            <div
              className="rounded-2xl px-4 py-3"
              style={{
                background: "color-mix(in srgb, var(--border) 40%, var(--bg) 60%)",
                borderBottomLeftRadius: "4px",
              }}
            >
              <TypingDots />
            </div>
          </div>
        )}
      </div>

      {err && <div className="text-sm text-red-600">{err}</div>}

      <div className="flex gap-2" style={{ borderTop: "1px solid var(--border)", paddingTop: "1rem" }}>
        <input
          ref={answerRef}
          type="text"
          value={answer}
          onChange={(e) => setAnswer(e.target.value)}
          onKeyDown={onAnswerKey}
          placeholder="Ваш ответ…"
          disabled={typing}
          style={{ fontSize: "14px" }}
          autoFocus
        />
        <button
          className="btn btn-primary"
          onClick={onSend}
          disabled={!answer.trim() || typing}
          style={{ padding: "10px 16px", flexShrink: 0 }}
        >
          <Send size={14} />
        </button>
      </div>
    </div>
  );
}

type ProposalPhaseProps = {
  proposal: Proposal;
  selectedTier: IntakeTier;
  setSelectedTier: (t: IntakeTier) => void;
  enrichedGoal: string;
  setEnrichedGoal: (v: string) => void;
  err: string | null;
  onConfirm: () => void;
};

function ProposalPhase({
  proposal,
  selectedTier,
  setSelectedTier,
  enrichedGoal,
  setEnrichedGoal,
  err,
  onConfirm,
}: ProposalPhaseProps) {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="font-serif text-xl font-semibold tracking-tight mb-1">
          Предложение
        </h2>
        <p className="text-sm" style={{ color: "var(--fg)", opacity: 0.75 }}>
          {proposal.rationale}
        </p>
      </div>

      <div className="space-y-2">
        <label className="text-sm font-medium">Уточнённая цель</label>
        <textarea
          rows={3}
          value={enrichedGoal}
          onChange={(e) => setEnrichedGoal(e.target.value)}
          className="resize-none"
          style={{ fontSize: "14px" }}
        />
      </div>

      <div className="space-y-2">
        <span className="text-sm font-medium">Тип анализа</span>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {TIERS.map((t) => {
            const active = selectedTier === t.id;
            const suggested = proposal.tier === t.id;
            return (
              <button
                key={t.id}
                type="button"
                onClick={() => setSelectedTier(t.id)}
                className="relative text-left rounded-lg p-4 transition-all active:scale-[0.98]"
                style={{
                  background: "var(--card)",
                  border: active ? "1px solid var(--fg)" : "1px solid var(--border)",
                  boxShadow: active
                    ? "0 0 0 1px var(--fg)"
                    : "0 1px 2px rgb(0 0 0 / 0.04)",
                }}
              >
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium">{t.label}</span>
                  {suggested && (
                    <span
                      className="text-[10px] font-medium px-1.5 py-0.5 rounded-full"
                      style={{
                        background: "var(--accent-soft)",
                        color: "var(--accent)",
                        border: "1px solid color-mix(in srgb, var(--accent) 30%, transparent)",
                      }}
                    >
                      рекомендовано
                    </span>
                  )}
                </div>
                <div className="mt-1 text-xs muted">
                  {t.time} · {t.price}
                </div>
                {active && (
                  <Check
                    size={16}
                    className="absolute top-3 right-3"
                    style={{ color: "var(--fg)" }}
                  />
                )}
              </button>
            );
          })}
        </div>
      </div>

      {err && <div className="text-sm text-red-600">{err}</div>}

      <div
        className="flex justify-end pt-4"
        style={{ borderTop: "1px solid var(--border)" }}
      >
        <button
          className="btn btn-primary"
          onClick={onConfirm}
          style={{ padding: "10px 24px" }}
        >
          <Play size={14} />
          Запустить
        </button>
      </div>
    </div>
  );
}
