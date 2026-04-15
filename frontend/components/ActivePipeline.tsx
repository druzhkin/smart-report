"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { RefreshCw } from "lucide-react";

type Running = { id: string; goal: string; phase: string; progress: number };

const PHASES = ["analyst", "scouts", "bisociator", "summarizer"];

export function ActivePipeline() {
  const [run, setRun] = useState<Running | null>(null);

  useEffect(() => {
    let alive = true;
    async function tick() {
      try {
        const r = await fetch("/api/reports").then((x) => x.json());
        const latest = r[0];
        if (!latest) return;
        const s = await fetch(`/api/research/${encodeURIComponent(latest.id)}/status`)
          .then((x) => (x.ok ? x.json() : null))
          .catch(() => null);
        if (!alive) return;
        if (s?.status === "running") {
          const idx = PHASES.indexOf(s.phase);
          const progress = idx >= 0 ? ((idx + 1) / PHASES.length) * 100 : 15;
          setRun({ id: latest.id, goal: latest.goal, phase: s.phase, progress });
        } else {
          setRun(null);
        }
      } catch {}
    }
    tick();
    const iv = setInterval(tick, 5000);
    return () => {
      alive = false;
      clearInterval(iv);
    };
  }, []);

  if (!run) return null;

  return (
    <div className="px-4 py-6 border-t" style={{ borderColor: "var(--border)" }}>
      <h3 className="px-3 text-xs font-medium muted uppercase tracking-widest mb-3">
        Active Pipeline
      </h3>
      <Link
        href={`/report/${encodeURIComponent(run.id)}`}
        className="block bg-white border border-zinc-200/80 rounded-md p-3 shadow-sm hover:shadow-md transition-shadow relative overflow-hidden group cursor-pointer active:scale-[0.98]"
      >
        <div className="flex items-start justify-between mb-2">
          <span className="text-xs font-medium text-zinc-900 line-clamp-1 group-hover:text-blue-600 transition-colors">
            {run.goal}
          </span>
          <span className="flex h-2 w-2 relative mt-1">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-500" />
          </span>
        </div>
        <div className="flex items-center gap-2 text-xs text-zinc-600">
          <RefreshCw size={11} className="animate-spin text-blue-500" />
          {run.phase}
        </div>
        <div className="w-full bg-zinc-100 rounded-full h-1 mt-3 relative overflow-hidden">
          <div
            className="bg-zinc-800 h-1 rounded-full relative z-10 transition-all duration-1000 ease-in-out"
            style={{ width: `${run.progress}%` }}
          >
            <div className="absolute top-0 left-0 w-full h-full bg-gradient-to-r from-transparent via-white/40 to-transparent animate-shimmer" />
          </div>
        </div>
      </Link>
    </div>
  );
}
