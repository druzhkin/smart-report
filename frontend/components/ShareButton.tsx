"use client";
import { useState } from "react";
import { Check } from "lucide-react";

export function ShareButton() {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(window.location.href);
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        } catch {}
      }}
      className="flex items-center gap-2 px-3 py-1.5 text-xs font-medium text-white bg-zinc-900 border border-zinc-900 rounded hover:bg-zinc-800 active:scale-[0.98] transition-all shadow-sm hover:shadow-md"
    >
      {copied ? <><Check size={12} /> Скопировано</> : "Поделиться"}
    </button>
  );
}
