"use client";

import { useState } from "react";
import { Copy, Check, ChevronDown, ChevronRight, RefreshCw, Lightbulb, Compass } from "lucide-react";
import type { ResearchPrompt } from "@/lib/apiV4";

export function PromptCard({
  prompt,
  onRegenerate,
  busy,
}: {
  prompt: ResearchPrompt;
  onRegenerate?: () => void;
  busy?: boolean;
}) {
  const [copied, setCopied] = useState(false);
  const [showReasoning, setShowReasoning] = useState(false);
  const [showTips, setShowTips] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(prompt.full_prompt);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      setCopied(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="card" style={{ padding: "1.5rem" }}>
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Compass size={16} className="text-blue-500" />
            <h3 className="font-serif text-lg font-semibold tracking-tight">
              Research-промт
            </h3>
          </div>
          <button
            className="btn"
            onClick={copy}
            aria-label="Копировать промт"
          >
            {copied ? (
              <>
                <Check size={14} className="text-emerald-500" />
                Скопировано
              </>
            ) : (
              <>
                <Copy size={14} />
                Копировать промт
              </>
            )}
          </button>
        </div>

        <pre
          className="whitespace-pre-wrap font-sans text-sm leading-relaxed p-4 rounded-lg"
          style={{
            background: "color-mix(in srgb, var(--border) 30%, var(--bg) 70%)",
            color: "var(--fg)",
          }}
        >
          {prompt.full_prompt}
        </pre>

        {prompt.key_entities.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {prompt.key_entities.map((e) => (
              <span
                key={e}
                className="text-[11px] px-2 py-0.5 rounded-full"
                style={{
                  background: "var(--accent-soft)",
                  color: "var(--accent)",
                  border: "1px solid color-mix(in srgb, var(--accent) 25%, transparent)",
                }}
              >
                {e}
              </span>
            ))}
          </div>
        )}
      </div>

      <Collapsible
        open={showReasoning}
        onToggle={() => setShowReasoning((v) => !v)}
        icon={<Lightbulb size={14} className="text-amber-500" />}
        label="Почему именно так"
      >
        <p className="text-sm leading-relaxed muted">{prompt.reasoning}</p>
        {prompt.expected_structure.length > 0 && (
          <div className="mt-3">
            <div className="text-xs font-semibold uppercase tracking-wider muted mb-1.5">
              Ожидаемая структура ответа
            </div>
            <ul className="text-sm space-y-1">
              {prompt.expected_structure.map((s, i) => (
                <li key={i} className="flex gap-2">
                  <span className="muted">{i + 1}.</span>
                  <span>{s}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </Collapsible>

      <Collapsible
        open={showTips}
        onToggle={() => setShowTips((v) => !v)}
        icon={<Compass size={14} className="text-emerald-500" />}
        label="Подсказка по инструменту"
      >
        <p className="text-sm leading-relaxed muted">{prompt.tips_for_search}</p>
      </Collapsible>

      {onRegenerate && (
        <div className="flex justify-start">
          <button
            className="btn"
            onClick={onRegenerate}
            disabled={busy}
          >
            <RefreshCw size={13} className={busy ? "animate-spin" : ""} />
            {busy ? "Генерирую…" : "Перегенерировать"}
          </button>
        </div>
      )}
    </div>
  );
}

function Collapsible({
  open,
  onToggle,
  icon,
  label,
  children,
}: {
  open: boolean;
  onToggle: () => void;
  icon: React.ReactNode;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="card" style={{ padding: "1rem" }}>
      <button
        className="flex items-center gap-2 w-full text-left"
        onClick={onToggle}
      >
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        {icon}
        <span className="text-sm font-medium">{label}</span>
      </button>
      {open && <div className="mt-3 pl-6">{children}</div>}
    </div>
  );
}
