"use client";

import { LivePipeline } from "@/components/LivePipeline";
import { SectionKicker } from "./SectionKicker";

type V4PhaseStatus = "done" | "active" | "waiting" | "pending";

type Props = {
  stage: "prompt" | "analyzer" | "synthesizer";
  title?: string;
  hint?: string;
};

const DEFAULTS: Record<Props["stage"], { title: string; hint: string; status: Record<string, V4PhaseStatus> }> = {
  prompt: {
    title: "Prompt Master формулирует research-промт",
    hint: "Opus-4.7 разбирает ваш вопрос на измерения, называет entities и источники. Обычно 20–40 секунд.",
    status: { prompt: "active", external: "pending", analyzer: "pending", synth: "pending" },
  },
  analyzer: {
    title: "Analyzer критикует загруженные отчёты",
    hint: "Ищет консенсус, противоречия, пробелы и неподтверждённые цифры. Обычно 40–90 секунд.",
    status: { prompt: "done", external: "done", analyzer: "active", synth: "pending" },
  },
  synthesizer: {
    title: "Synthesizer собирает финальный отчёт",
    hint: "Сводит три источника + добор в один документ, ранжирует факторы, выделяет key numbers. Обычно 40–90 секунд.",
    status: { prompt: "done", external: "done", analyzer: "done", synth: "active" },
  },
};

export function ProcessingOverlay({ stage, title, hint }: Props) {
  const d = DEFAULTS[stage];
  return (
    <div
      className="v4"
      data-theme="v4"
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(10, 10, 8, 0.35)",
        backdropFilter: "blur(2px)",
        WebkitBackdropFilter: "blur(2px)",
        zIndex: 100,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 24,
      }}
    >
      <div
        style={{
          background: "var(--v4-paper)",
          border: "1px solid var(--v4-ink)",
          boxShadow: "8px 8px 0 var(--v4-paper-3)",
          padding: 32,
          minWidth: 640,
          maxWidth: 820,
          width: "100%",
        }}
      >
        <SectionKicker>Идёт обработка</SectionKicker>
        <h3
          className="v4-display"
          style={{ marginTop: 8, marginBottom: 20, fontSize: 28, lineHeight: 1.15 }}
        >
          {title ?? d.title}
        </h3>
        <LivePipeline
          events={[]}
          goal={undefined}
          mode="v4"
          compact
          phaseStatus={d.status}
        />
        <p
          style={{
            marginTop: 18,
            fontSize: 13,
            color: "var(--v4-ink-3)",
            lineHeight: 1.55,
          }}
        >
          {hint ?? d.hint} Не закрывайте вкладку — результат не сохранится при прерывании.
        </p>
      </div>
    </div>
  );
}
