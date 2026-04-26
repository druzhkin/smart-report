"use client";

import { useMemo } from "react";
import { Library, ArrowRight } from "lucide-react";
import type { Block } from "@/lib/api";

type SourceItem = {
  id: number;
  title: string;
  url: string;
  domain: string;
  year?: number;
  source_type?: string;
};

function domainOf(url: string): string {
  try {
    const u = new URL(url.startsWith("http") ? url : `https://${url}`);
    return u.hostname.replace(/^www\./, "");
  } catch {
    if (url.startsWith("doi:") || url.startsWith("10.")) return "doi.org";
    return url.slice(0, 24);
  }
}

export function SourcesSection({ blocks, limit = 8 }: { blocks: Block[]; limit?: number }) {
  const sources = useMemo<SourceItem[]>(() => {
    const seen = new Map<string, SourceItem>();
    let idx = 1;
    for (const b of blocks) {
      for (const f of b.findings || []) {
        const key = f.source;
        if (!key || seen.has(key)) continue;
        const fAny = f as any;
        seen.set(key, {
          id: idx++,
          title: fAny.source_label || f.claim,
          url: f.source,
          domain: domainOf(f.source),
          year: fAny.year,
          source_type: f.source_type,
        });
      }
    }
    return Array.from(seen.values());
  }, [blocks]);

  if (sources.length === 0) return null;

  const visible = sources.slice(0, limit);
  const extra = sources.length - visible.length;

  return (
    <section id="sec-sources" className="card p-6 md:p-8">
      <h3 className="text-lg font-semibold mb-5 flex items-center gap-2">
        <Library size={18} />
        Synthesized Sources
        <span className="muted text-xs font-normal ml-1">· {sources.length}</span>
      </h3>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {visible.map((s) => (
          <a
            key={s.id}
            href={s.url.startsWith("http") ? s.url : `https://doi.org/${s.url.replace(/^doi:/, "")}`}
            target="_blank"
            rel="noreferrer"
            className="group block p-4 rounded-lg transition-all active:scale-[0.98]"
            style={{
              background: "color-mix(in srgb, var(--card) 60%, var(--bg) 40%)",
              border: "1px solid var(--border)",
            }}
          >
            <div className="flex items-start gap-3">
              <div
                className="flex-shrink-0 w-6 h-6 rounded flex items-center justify-center text-xs font-medium mt-0.5 group-hover:bg-[var(--accent-soft)] group-hover:text-[var(--accent)] transition-colors"
                style={{ background: "color-mix(in srgb, var(--border) 70%, transparent)" }}
              >
                {s.id}
              </div>
              <div className="min-w-0">
                <h4 className="text-sm font-medium line-clamp-2 leading-snug group-hover:text-[var(--accent)] transition-colors">
                  {s.title}
                </h4>
                <div className="mt-2 flex items-center gap-2 text-xs muted">
                  <span
                    className="px-1.5 py-0.5 rounded font-medium"
                    style={{ background: "var(--card)", border: "1px solid var(--border)", color: "var(--fg)" }}
                  >
                    {s.domain}
                  </span>
                  {s.year ? (
                    <>
                      <span>•</span>
                      <span>{s.year}</span>
                    </>
                  ) : null}
                  {s.source_type?.startsWith("primary") ? (
                    <>
                      <span>•</span>
                      <span className="text-emerald-600 font-medium">primary</span>
                    </>
                  ) : null}
                </div>
              </div>
            </div>
          </a>
        ))}
        {extra > 0 && (
          <div
            className="flex items-center justify-center p-4 rounded-lg text-sm font-medium muted hover:text-[var(--fg)] transition-colors"
            style={{ border: "1px dashed var(--border)" }}
          >
            <span className="flex items-center gap-2">
              + ещё {extra} {extra === 1 ? "источник" : "источников"}
              <ArrowRight size={14} />
            </span>
          </div>
        )}
      </div>
    </section>
  );
}
