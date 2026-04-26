"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronDown, EyeOff, Zap, Link2 } from "lucide-react";
import type { Analogy, AssumptionInversion, Block, BlockHeader, BlockInversions } from "@/lib/api";
import { DeepenForm } from "@/components/DeepenForm";

function prioClass(p?: string) {
  if (p === "high") return "prio-bar-high";
  if (p === "medium") return "prio-bar-medium";
  if (p === "low") return "prio-bar-low";
  return "";
}
function prioDot(p?: string) {
  if (p === "high") return "🔴";
  if (p === "medium") return "🟡";
  if (p === "low") return "🟢";
  return "⚪";
}

function depBorderClass(dep: string) {
  if (dep === "critical") return "border-red-400";
  if (dep === "important") return "border-amber-400";
  return "border-zinc-300 dark:border-zinc-600";
}

function probChipClass(prob: string) {
  if (prob === "high") return "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300";
  if (prob === "medium") return "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300";
  return "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400";
}

function depChipClass(dep: string) {
  if (dep === "critical") return "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300";
  if (dep === "important") return "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300";
  return "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400";
}

export function BlockCard({
  block,
  header,
  inversions,
  selected,
  connectMode,
  onSelect,
  onDeepen,
  onDismiss,
}: {
  block: Block;
  header?: BlockHeader;
  inversions?: BlockInversions | null;
  selected?: boolean;
  connectMode?: boolean;
  onSelect: (cell: string) => void;
  onDeepen: (cell: string, focus: string) => Promise<void>;
  onDismiss: (cell: string) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [deepenOpen, setDeepenOpen] = useState(false);

  return (
    <div
      className={
        "card overflow-hidden " +
        prioClass(header?.priority) +
        (selected ? " ring-2 ring-brand-500" : "") +
        (connectMode ? " cursor-pointer" : "")
      }
      onClick={() => connectMode && onSelect(block.cell)}
    >
      <div className="p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="text-xs muted">{prioDot(header?.priority)} {block.cell}</div>
            <div className="mt-1 font-medium leading-snug">
              {header?.one_liner ?? block.summary.split("\n")[0]}
            </div>
            {header?.strongest_number && (
              <div className="mt-1 text-sm text-brand-600 dark:text-brand-100">
                📊 {header.strongest_number}
              </div>
            )}
            {header?.main_gap && (
              <div className="mt-1 text-xs muted">Пробел: {header.main_gap}</div>
            )}
          </div>
          <div className="flex items-center gap-1 shrink-0" onClick={(e) => e.stopPropagation()}>
            <button
              className="btn !px-2"
              title="Копай глубже"
              onClick={() => setDeepenOpen((v) => !v)}
            >
              <Zap size={14} /> Копай
            </button>
            <button
              className="btn !px-2"
              title="Не интересно"
              onClick={() => onDismiss(block.cell)}
            >
              <EyeOff size={14} />
            </button>
            <button
              className="btn !px-2"
              onClick={() => setOpen((v) => !v)}
              title={open ? "Свернуть" : "Развернуть"}
            >
              <ChevronDown
                size={14}
                style={{
                  transform: open ? "rotate(180deg)" : "none",
                  transition: "transform .2s",
                }}
              />
            </button>
          </div>
        </div>
      </div>

      <AnimatePresence initial={false}>
        {deepenOpen && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="border-t"
            style={{ borderColor: "var(--border)" }}
          >
            <DeepenForm
              block={block}
              onSubmit={async (focus) => {
                await onDeepen(block.cell, focus);
                setDeepenOpen(false);
              }}
              onClose={() => setDeepenOpen(false)}
            />
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="border-t"
            style={{ borderColor: "var(--border)" }}
          >
            <div className="p-4 space-y-4 text-sm">
              <div className="whitespace-pre-wrap leading-relaxed">{block.summary}</div>
              {block.unverified_numerics && block.unverified_numerics.length > 0 && (
                <div
                  className="text-xs muted border-l-2 pl-3 py-1"
                  style={{ borderColor: "var(--border)" }}
                  title="Это значение отсутствует дословно в источниках. Вероятно, аналитик агрегировал его из нескольких фрагментов."
                >
                  <span className="mr-1">∑</span>
                  Синтезированные числа:{" "}
                  {block.unverified_numerics.map((n, i) => (
                    <span key={i}>
                      <span className="underline decoration-dotted decoration-current underline-offset-4">
                        {n}
                      </span>
                      {i < block.unverified_numerics!.length - 1 ? ", " : ""}
                    </span>
                  ))}
                </div>
              )}
              {block.findings.length > 0 && (
                <div>
                  <div className="font-medium mb-1">Источники</div>
                  <ul className="space-y-1">
                    {block.findings.map((f, i) => (
                      <li key={i} className="text-xs">
                        {f.has_numbers && "📊 "}
                        {f.claim}{" "}
                        <a
                          href={f.source}
                          target="_blank"
                          className="text-brand-600 underline break-all"
                          rel="noreferrer"
                        >
                          [{f.source_type}]
                        </a>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {block.assumptions.length > 0 && (
                <div>
                  <div className="font-medium mb-1">Допущения</div>
                  <ul className="list-disc ml-5 text-xs muted">
                    {block.assumptions.map((a, i) => <li key={i}>{a}</li>)}
                  </ul>
                </div>
              )}
              {block.gaps.length > 0 && (
                <div>
                  <div className="font-medium mb-1">Пробелы</div>
                  <ul className="list-disc ml-5 text-xs muted">
                    {block.gaps.map((g, i) => <li key={i}>{g}</li>)}
                  </ul>
                </div>
              )}
              {block.analogies && block.analogies.length > 0 && (
                <div>
                  <div className="text-xs uppercase tracking-wide muted mb-2">Исторические аналогии</div>
                  <div className="space-y-2">
                    {block.analogies.map((a: Analogy, i: number) => (
                      <div
                        key={i}
                        className="border-l-2 pl-3 py-1 text-xs"
                        style={{ borderColor: "var(--brand-500, #6366f1)" }}
                      >
                        {a.location && (
                          <div className="font-medium text-sm">{a.location}</div>
                        )}
                        <div className="muted mb-1">{a.situation}</div>
                        {((a.matched && a.matched.length > 0) || (a.differed && a.differed.length > 0)) && (
                          <div className="grid grid-cols-2 gap-2 mb-1">
                            {a.matched && a.matched.length > 0 && (
                              <div>
                                <span className="text-xs font-medium" style={{ color: "var(--green-600, #16a34a)" }}>Что совпадает</span>
                                <ul className="list-disc ml-4 mt-0.5">
                                  {a.matched.map((m, j) => <li key={j}>{m}</li>)}
                                </ul>
                              </div>
                            )}
                            {a.differed && a.differed.length > 0 && (
                              <div>
                                <span className="text-xs font-medium" style={{ color: "var(--amber-600, #d97706)" }}>Что отличается</span>
                                <ul className="list-disc ml-4 mt-0.5">
                                  {a.differed.map((d, j) => <li key={j}>{d}</li>)}
                                </ul>
                              </div>
                            )}
                          </div>
                        )}
                        <div className="font-medium">{a.lesson}</div>
                        {a.confidence && a.confidence !== "high" && (
                          <span className="inline-block mt-1 px-1.5 py-0.5 rounded text-xs muted border" style={{ borderColor: "var(--border)" }}>
                            {a.confidence}
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {inversions && inversions.inversions.length > 0 && (
                <div>
                  <div className="text-xs uppercase tracking-wide muted mb-2">Проверка допущений · quadrant crunch</div>
                  {inversions.unfalsifiable_flag && (
                    <div className="mb-2 px-3 py-1.5 text-xs border border-amber-300 bg-amber-50 dark:bg-amber-900/20 dark:border-amber-700 rounded">
                      Внимание: вывод может быть нефальсифицируем — ни одно допущение не является критически несущим.
                    </div>
                  )}
                  <div className="space-y-2">
                    {inversions.inversions.map((inv: AssumptionInversion, i: number) => (
                      <div
                        key={i}
                        className={`border-l-2 pl-3 py-1.5 text-xs space-y-1 ${depBorderClass(inv.dependency)}`}
                      >
                        <div><span className="muted">Допущение: </span>{inv.assumption}</div>
                        <div><span className="muted">А если нет? </span><span className="font-semibold">{inv.inversion}</span></div>
                        <div><span className="muted">Последствие: </span>{inv.consequence}</div>
                        <div className="flex flex-wrap gap-1.5 items-center">
                          <span className={`inline-block px-1.5 py-0.5 rounded text-xs font-medium ${probChipClass(inv.probability)}`}>
                            {inv.probability}
                          </span>
                          <span className={`inline-block px-1.5 py-0.5 rounded text-xs font-medium ${depChipClass(inv.dependency)}`}>
                            {inv.dependency}
                          </span>
                        </div>
                        <div><span className="muted">Ранний сигнал: </span>{inv.early_signal}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
