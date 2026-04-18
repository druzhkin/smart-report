"use client";

import { useState } from "react";
import { Copy, Check, AlertCircle, Sparkles } from "lucide-react";
import type { FollowupPrompt } from "@/lib/apiV4";

const INTENT_LABEL: Record<string, string> = {
  fill_gap: "Закрыть gap",
  verify_number: "Проверить цифру",
  resolve_conflict: "Разрешить конфликт",
};

const TOOL_LABEL: Record<string, string> = {
  perplexity: "Perplexity",
  openai_dr: "OpenAI DR",
  claude: "Claude",
};

export function FollowupList({ prompts }: { prompts: FollowupPrompt[] }) {
  const must = prompts.filter((p) => p.priority === "must");
  const nice = prompts.filter((p) => p.priority === "nice");

  if (prompts.length === 0) {
    return (
      <div className="text-sm muted py-6 text-center">
        Followup-промтов нет — критика не нашла material gaps.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {must.length > 0 && (
        <Section
          title="Обязательные"
          subtitle="Без этих цифр финальный отчёт будет слабее входных"
          icon={<AlertCircle size={14} className="text-rose-500" />}
          items={must}
        />
      )}
      {nice.length > 0 && (
        <Section
          title="Желательные"
          subtitle="Улучшат качество, но не критичны"
          icon={<Sparkles size={14} className="text-amber-500" />}
          items={nice}
        />
      )}
    </div>
  );
}

function Section({
  title,
  subtitle,
  icon,
  items,
}: {
  title: string;
  subtitle: string;
  icon: React.ReactNode;
  items: FollowupPrompt[];
}) {
  return (
    <div>
      <div className="flex items-baseline gap-2 mb-3">
        {icon}
        <h3 className="font-serif text-lg font-semibold tracking-tight">{title}</h3>
        <span className="text-xs muted">· {subtitle}</span>
        <span className="ml-auto text-xs muted">{items.length}</span>
      </div>
      <div className="space-y-3">
        {items.map((p) => (
          <FollowupCard key={p.prompt_id} prompt={p} />
        ))}
      </div>
    </div>
  );
}

function FollowupCard({ prompt }: { prompt: FollowupPrompt }) {
  const [copied, setCopied] = useState(false);
  const [done, setDone] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(prompt.prompt);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      setCopied(false);
    }
  }

  return (
    <div
      className="card"
      style={{
        padding: "1rem",
        opacity: done ? 0.55 : 1,
      }}
    >
      <div className="flex flex-wrap items-center gap-2 mb-2">
        <span
          className="text-[10px] uppercase tracking-wider font-semibold px-2 py-0.5 rounded-full"
          style={{
            background: "var(--accent-soft)",
            color: "var(--accent)",
          }}
        >
          {INTENT_LABEL[prompt.intent] || prompt.intent}
        </span>
        <span className="text-[11px] px-2 py-0.5 rounded-full bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300">
          {TOOL_LABEL[prompt.suggested_tool] || prompt.suggested_tool}
        </span>
        {prompt.suggested_source_site && (
          <span className="text-[11px] px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 font-mono">
            {prompt.suggested_source_site}
          </span>
        )}
        <span className="ml-auto text-[11px] muted">→ {prompt.target_info}</span>
      </div>

      <pre
        className="whitespace-pre-wrap font-sans text-[13px] leading-relaxed p-3 rounded-lg"
        style={{
          background: "color-mix(in srgb, var(--border) 25%, var(--bg) 75%)",
        }}
      >
        {prompt.prompt}
      </pre>

      <div className="flex items-center gap-3 mt-3">
        <button className="btn" onClick={copy} disabled={done}>
          {copied ? (
            <>
              <Check size={13} className="text-emerald-500" />
              Скопировано
            </>
          ) : (
            <>
              <Copy size={13} />
              Копировать
            </>
          )}
        </button>
        <label className="flex items-center gap-2 text-sm muted cursor-pointer select-none">
          <input
            type="checkbox"
            checked={done}
            onChange={(e) => setDone(e.target.checked)}
            style={{ width: "auto", padding: 0 }}
          />
          Уже сделал
        </label>
      </div>
    </div>
  );
}
