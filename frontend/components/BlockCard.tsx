"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronDown, EyeOff, Zap, Link2 } from "lucide-react";
import type { Block, BlockHeader } from "@/lib/api";
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

export function BlockCard({
  block,
  header,
  selected,
  connectMode,
  onSelect,
  onDeepen,
  onDismiss,
}: {
  block: Block;
  header?: BlockHeader;
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
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
