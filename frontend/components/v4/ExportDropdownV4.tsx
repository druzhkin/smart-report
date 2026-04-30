"use client";

import { useState } from "react";
import { exportUrl, generateGammaPptx } from "@/lib/apiV4";
import {
  Archive,
  ChevronDown,
  FileCode,
  FileDown,
  FileSpreadsheet,
  FileText,
  LayoutTemplate,
  Presentation,
  Sparkles,
} from "lucide-react";

type Item = {
  fmt: string;
  label: string;
  Icon: any;
  accent: string;
};

const ITEMS: Item[] = [
  { fmt: "premium-client-package", label: "Клиентский пакет ZIP", Icon: Sparkles, accent: "text-[#B08D57]" },
  { fmt: "premium-package", label: "Премиальный черновик ZIP", Icon: Archive, accent: "text-[#B08D57]" },
  { fmt: "next-research-brief", label: "План добора MD", Icon: FileText, accent: "text-[#B08D57]" },
  { fmt: "premium-docx", label: "Премиальный отчёт DOCX", Icon: Sparkles, accent: "text-[#B08D57]" },
  { fmt: "premium-pptx", label: "Премиальная презентация PPTX", Icon: Presentation, accent: "text-[#B08D57]" },
  { fmt: "docx", label: "Клиентский отчёт DOCX", Icon: FileText, accent: "text-blue-600" },
  { fmt: "pptx", label: "Простая презентация PPTX", Icon: Presentation, accent: "text-orange-600" },
  { fmt: "onepager", label: "One-pager HTML", Icon: LayoutTemplate, accent: "text-[#1B3A5C]" },
  { fmt: "md", label: "Markdown", Icon: FileSpreadsheet, accent: "text-emerald-600" },
  { fmt: "json", label: "Клиентский отчёт JSON", Icon: FileCode, accent: "text-purple-600" },
  { fmt: "sources-csv", label: "Источники CSV", Icon: FileSpreadsheet, accent: "text-emerald-600" },
  { fmt: "facts-csv", label: "Факты CSV", Icon: FileSpreadsheet, accent: "text-emerald-600" },
  { fmt: "data-pack", label: "Полный data pack ZIP", Icon: Archive, accent: "text-slate-700" },
  { fmt: "audit-json", label: "Аудит JSON", Icon: FileCode, accent: "text-slate-500" },
];

export function ExportDropdownV4({ id }: { id: string }) {
  const [open, setOpen] = useState(false);
  const [gammaState, setGammaState] = useState<"idle" | "generating" | "error">("idle");
  const [gammaError, setGammaError] = useState<string | null>(null);

  async function handleGamma() {
    setGammaState("generating");
    setGammaError(null);
    try {
      const url = await generateGammaPptx(id);
      window.open(url, "_blank", "noopener,noreferrer");
      setGammaState("idle");
      setOpen(false);
    } catch (err) {
      setGammaError(err instanceof Error ? err.message : String(err));
      setGammaState("error");
    }
  }

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
        <FileDown size={14} /> Export
        <ChevronDown
          size={12}
          className={"transition-transform duration-200 " + (open ? "rotate-180" : "")}
        />
      </button>
      <div
        className={
          "absolute right-0 mt-2 w-64 card p-1.5 space-y-0.5 shadow-[0_8px_30px_rgb(0,0,0,0.08)] z-50 transition-all duration-150 origin-top-right " +
          (open ? "opacity-100 visible scale-100" : "opacity-0 invisible scale-95")
        }
      >
        <button
          type="button"
          onClick={handleGamma}
          disabled={gammaState === "generating"}
          className="flex w-full items-center gap-3 px-2.5 py-2 text-xs font-medium rounded-md transition-colors hover:bg-[var(--accent-soft)] disabled:cursor-wait disabled:opacity-60"
        >
          <Sparkles size={16} className="text-fuchsia-600" />
          <span className="flex-1 text-left">
            {gammaState === "generating" ? "Gamma is building..." : "Gamma PPTX"}
          </span>
        </button>
        {gammaState === "error" && gammaError && (
          <div className="px-2.5 py-1 text-[11px] text-red-700">{gammaError}</div>
        )}
        {ITEMS.map((item) => {
          const { Icon, accent, label, fmt } = item;
          return (
            <a
              key={fmt}
              href={exportUrl(id, fmt, { allowDraft: fmt !== "premium-client-package" })}
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
