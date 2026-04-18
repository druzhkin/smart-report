"use client";

// Minimal v4-flavoured export dropdown. Mirrors the visual of ExportButtons
// but points at `/api/v4/sessions/{id}/export?format=X` (query-param shape).
// Not a fork of ExportButtons — ExportButtons carries v3-specific Gamma
// polling hardcoded to /api/research/{id}/... which doesn't apply here.

import { useState } from "react";
import { exportUrl } from "@/lib/apiV4";
import {
  FileDown,
  ChevronDown,
  FileText,
  FileSpreadsheet,
  FileCode,
  Presentation,
  Sparkles,
  LayoutTemplate,
} from "lucide-react";

type Item = {
  fmt: string;
  label: string;
  Icon: any;
  accent: string;
};

const ITEMS: Item[] = [
  { fmt: "onepager", label: "One-pager (Word, 1 стр.)", Icon: LayoutTemplate, accent: "text-[#1B3A5C]" },
  { fmt: "gamma-pptx", label: "✨ Gamma Presentation (.pptx)", Icon: Sparkles, accent: "text-fuchsia-600" },
  { fmt: "gamma-pdf", label: "✨ Gamma Presentation (.pdf)", Icon: Sparkles, accent: "text-fuchsia-600" },
  { fmt: "docx", label: "Word Document (.docx)", Icon: FileText, accent: "text-blue-600" },
  { fmt: "pptx", label: "Presentation (.pptx)", Icon: Presentation, accent: "text-orange-600" },
  { fmt: "md", label: "Markdown (.md)", Icon: FileSpreadsheet, accent: "text-emerald-600" },
  { fmt: "json", label: "Raw JSON (.json)", Icon: FileCode, accent: "text-purple-600" },
];

export function ExportDropdownV4({ id }: { id: string }) {
  const [open, setOpen] = useState(false);

  return (
    <div
      className="relative"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <button
        className="btn"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
      >
        <FileDown size={14} /> Экспорт
        <ChevronDown
          size={12}
          className={"transition-transform duration-200 " + (open ? "rotate-180" : "")}
        />
      </button>
      <div
        className={
          "absolute right-0 mt-2 w-60 card p-1.5 space-y-0.5 shadow-[0_8px_30px_rgb(0,0,0,0.08)] z-50 transition-all duration-150 origin-top-right " +
          (open ? "opacity-100 visible scale-100" : "opacity-0 invisible scale-95")
        }
      >
        {ITEMS.map((item) => {
          const { Icon, accent, label, fmt } = item;
          return (
            <a
              key={fmt}
              href={exportUrl(id, fmt)}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-3 px-2.5 py-2 text-xs font-medium rounded-md transition-colors hover:bg-[var(--accent-soft)]"
            >
              <Icon size={16} className={accent} />
              <span className="flex-1">{label}</span>
            </a>
          );
        })}
      </div>
    </div>
  );
}
