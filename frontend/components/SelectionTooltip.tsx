"use client";
import { useEffect, useRef, useState } from "react";
import { Wand2 } from "lucide-react";

export function SelectionTooltip({
  containerSelector,
  onExpand,
}: {
  containerSelector: string;
  onExpand: (text: string, cell: string | null) => void;
}) {
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null);
  const [text, setText] = useState("");
  const [cell, setCell] = useState<string | null>(null);
  const ref = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    function onUp() {
      const sel = window.getSelection();
      if (!sel || sel.isCollapsed) {
        setPos(null);
        return;
      }
      const str = sel.toString().trim();
      if (str.length < 8 || str.length > 400) {
        setPos(null);
        return;
      }
      const container = document.querySelector(containerSelector);
      const anchor = sel.anchorNode?.parentElement;
      if (!container || !anchor || !container.contains(anchor)) {
        setPos(null);
        return;
      }
      const sectionEl = anchor.closest("[data-cell]") as HTMLElement | null;
      const rect = sel.getRangeAt(0).getBoundingClientRect();
      setText(str);
      setCell(sectionEl?.dataset.cell ?? null);
      setPos({ x: rect.left + rect.width / 2 + window.scrollX, y: rect.top + window.scrollY });
    }
    document.addEventListener("mouseup", onUp);
    document.addEventListener("selectionchange", () => {
      const sel = window.getSelection();
      if (!sel || sel.isCollapsed) setPos(null);
    });
    return () => document.removeEventListener("mouseup", onUp);
  }, [containerSelector]);

  if (!pos) return null;
  return (
    <button
      ref={ref}
      onMouseDown={(e) => {
        e.preventDefault();
        onExpand(text, cell);
        setPos(null);
        window.getSelection()?.removeAllRanges();
      }}
      className="absolute flex items-center gap-1.5 bg-zinc-900/95 backdrop-blur-md text-white px-3 py-1.5 rounded-lg shadow-xl text-xs font-medium whitespace-nowrap animate-float z-[60] hover:bg-zinc-800 active:scale-95 transition-all border border-zinc-700/50"
      style={{ left: pos.x, top: pos.y - 40, transform: "translate(-50%, 0)" }}
    >
      <Wand2 size={12} className="text-blue-400" />
      Копай глубже
    </button>
  );
}
