"use client";

import { useState } from "react";
import { exportUrl, gammaExportUrl } from "@/lib/api";
import { FileDown, ChevronDown, FileText, FileSpreadsheet, FileCode, Presentation, Sparkles, Loader2, LayoutTemplate } from "lucide-react";

type Item =
  | { kind: "file"; fmt: "md" | "docx" | "pptx" | "json" | "onepager" | "onepager.docx"; label: string; Icon: any; accent: string }
  | { kind: "gamma"; format: "pptx" | "pdf"; label: string; Icon: any; accent: string };

const ITEMS: Item[] = [
  { kind: "file", fmt: "onepager.docx", label: "One-pager (Word, 1 стр.)", Icon: LayoutTemplate, accent: "text-[#1B3A5C]" },
  { kind: "gamma", format: "pptx", label: "✨ Gamma Presentation (.pptx)", Icon: Sparkles, accent: "text-fuchsia-600" },
  { kind: "gamma", format: "pdf", label: "✨ Gamma Presentation (.pdf)", Icon: Sparkles, accent: "text-fuchsia-600" },
  { kind: "file", fmt: "docx", label: "Word Document (.docx)", Icon: FileText, accent: "text-blue-600" },
  { kind: "file", fmt: "pptx", label: "Presentation (.pptx)", Icon: Presentation, accent: "text-orange-600" },
  { kind: "file", fmt: "md", label: "Markdown (.md)", Icon: FileSpreadsheet, accent: "text-emerald-600" },
  { kind: "file", fmt: "json", label: "Raw JSON (.json)", Icon: FileCode, accent: "text-purple-600" },
];

export function ExportButtons({ id }: { id: string }) {
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [gammaBusy, setGammaBusy] = useState<null | "pptx" | "pdf">(null);

  async function handleGamma(format: "pptx" | "pdf", e: React.MouseEvent) {
    e.preventDefault();
    if (gammaBusy) return;
    // Open tab synchronously during the click so Chrome doesn't block it.
    const popup = window.open("about:blank", "_blank");
    if (popup) {
      popup.document.write(
        '<!doctype html><meta charset="utf-8"><title>Gamma</title>' +
        '<style>body{font-family:system-ui;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;color:#1B3A5C}</style>' +
        '<div>Готовлю презентацию в Gamma…</div>'
      );
    }
    setGammaBusy(format);
    setStatus("Собираю презентацию в Gamma…");
    try {
      const resp = await fetch(gammaExportUrl(id, format));
      const ct = resp.headers.get("content-type") || "";
      if (!resp.ok) {
        let msg = `Ошибка ${resp.status}`;
        try {
          const j = ct.includes("json") ? await resp.json() : null;
          if (j?.detail) msg = j.detail;
        } catch {}
        if (popup && !popup.closed) popup.close();
        setStatus(`Не получилось: ${msg}`);
        setGammaBusy(null);
        setTimeout(() => setStatus(null), 5000);
        return;
      }
      if (ct.includes("application/json")) {
        const j = await resp.json();
        // If we already have a downloadable file (cached or ready) — just download it.
        if (j.export_url) {
          if (popup && !popup.closed) popup.close();
          const a = document.createElement("a");
          a.href = j.export_url;
          a.target = "_blank";
          a.rel = "noreferrer";
          a.download = `${id}.gamma.${format}`;
          document.body.appendChild(a);
          a.click();
          a.remove();
          setStatus(j.status === "cached" ? "Скачиваю готовую презентацию…" : "Файл готов — скачивание начато.");
          setGammaBusy(null);
          setTimeout(() => setStatus(null), 4000);
          return;
        }
        if (j.gamma_url) {
          if (popup && !popup.closed) popup.location.href = j.gamma_url;
          else window.open(j.gamma_url, "_blank", "noopener");
        } else if (popup && !popup.closed) {
          popup.close();
        }
        if (j.generation_id && !j.export_url) {
          setStatus("Презентация открылась в Gamma. Готовлю файл для скачивания…");
          const start = Date.now();
          const poll = async () => {
            while (Date.now() - start < 10 * 60 * 1000) {
              await new Promise((r) => setTimeout(r, 5000));
              try {
                const s = await fetch(`/api/research/${id}/export/gamma/status/${j.generation_id}`);
                const sj = await s.json();
                if (sj.export_url) {
                  const a = document.createElement("a");
                  a.href = sj.export_url;
                  a.target = "_blank";
                  a.rel = "noreferrer";
                  a.download = `${id}.gamma.${format}`;
                  document.body.appendChild(a);
                  a.click();
                  a.remove();
                  setStatus("Файл готов — скачивание начато.");
                  setGammaBusy(null);
                  setTimeout(() => setStatus(null), 4000);
                  return;
                }
              } catch {}
            }
            setStatus("Файл ещё готовится — откройте ссылку Gamma и скачайте вручную.");
            setGammaBusy(null);
            setTimeout(() => setStatus(null), 6000);
          };
          poll();
          return;
        }
        setStatus(null);
        setGammaBusy(null);
        return;
      }
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${id}.gamma.${format}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      setStatus(null);
      setGammaBusy(null);
    } catch (err: any) {
      setStatus(`Не получилось: ${err?.message || err}`);
      setGammaBusy(null);
      setTimeout(() => setStatus(null), 5000);
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
          const key = item.kind === "gamma" ? `gamma-${item.format}` : item.fmt;
          const href =
            item.kind === "gamma"
              ? gammaExportUrl(id, item.format)
              : exportUrl(id, item.fmt);
          const { Icon, accent, label } = item;
          const isGamma = item.kind === "gamma";
          const thisBusy = isGamma && gammaBusy === item.format;
          const otherBusy = isGamma && !!gammaBusy && gammaBusy !== item.format;
          const disabled = isGamma && !!gammaBusy;
          return (
            <a
              key={key}
              href={disabled ? undefined : href}
              target="_blank"
              rel="noreferrer"
              onClick={isGamma ? (e) => handleGamma(item.format, e) : undefined}
              aria-disabled={disabled}
              className={
                "flex items-center gap-3 px-2.5 py-2 text-xs font-medium rounded-md transition-colors " +
                (disabled
                  ? "opacity-50 cursor-not-allowed pointer-events-none"
                  : "hover:bg-[var(--accent-soft)]")
              }
            >
              {thisBusy ? (
                <Loader2 size={16} className={accent + " animate-spin"} />
              ) : (
                <Icon size={16} className={accent} />
              )}
              <span className="flex-1">{label}</span>
              {thisBusy && <span className="text-[10px] text-fuchsia-600">генерация…</span>}
              {otherBusy && <span className="text-[10px] muted">ждите</span>}
            </a>
          );
        })}
      </div>
      {status && (
        <div className="absolute right-0 top-full mt-2 w-72 card p-2 text-xs shadow-lg z-50 flex items-start gap-2">
          {gammaBusy && <Loader2 size={14} className="text-fuchsia-600 animate-spin mt-0.5 shrink-0" />}
          <span>{status}</span>
        </div>
      )}
    </div>
  );
}
