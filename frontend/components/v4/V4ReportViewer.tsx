"use client";

import { ExternalLink, Award, Hash } from "lucide-react";
import type { FinalReport } from "@/lib/apiV4";

export function V4ReportViewer({ report }: { report: FinalReport }) {
  const exec = report.executive_summary;
  return (
    <div className="space-y-8">
      {/* Executive summary hero */}
      <section
        className="card relative overflow-hidden"
        style={{ padding: "1.75rem" }}
      >
        <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-violet-400 via-blue-500 to-emerald-400 opacity-60" />

        {exec.ranking && (
          <div className="flex items-center gap-2 mb-3">
            <Award size={14} className="text-amber-500" />
            <span
              className="text-[11px] uppercase tracking-wider font-semibold px-2 py-0.5 rounded-full"
              style={{
                background: "var(--accent-soft)",
                color: "var(--accent)",
              }}
            >
              Ranking
            </span>
            <span className="text-sm font-medium">{exec.ranking}</span>
          </div>
        )}

        <div className="font-serif text-lg md:text-xl leading-relaxed mb-5">
          {exec.main_answer}
        </div>

        {exec.top_findings.length > 0 && (
          <div className="space-y-2 mb-5">
            {exec.top_findings.map((f, i) => (
              <div key={i} className="flex items-start gap-3 text-sm">
                <span
                  className="font-semibold muted w-5 flex-shrink-0"
                  style={{ fontFamily: "var(--font-serif, Newsreader)" }}
                >
                  {i + 1}.
                </span>
                <span className="flex-1">{f}</span>
              </div>
            ))}
          </div>
        )}

        {exec.key_numbers.length > 0 && (
          <div
            className="grid grid-cols-1 md:grid-cols-3 gap-3 mt-4 pt-4"
            style={{ borderTop: "1px solid var(--border)" }}
          >
            {exec.key_numbers.map((kn, i) => (
              <div key={i} className="space-y-0.5">
                <div className="flex items-baseline gap-2">
                  <Hash size={10} className="text-indigo-400" />
                  <span className="font-mono font-semibold text-lg text-indigo-600">
                    {kn.value}
                  </span>
                </div>
                <div className="text-[13px] font-medium">{kn.metric}</div>
                <div className="text-[11px] muted">{kn.source}</div>
              </div>
            ))}
          </div>
        )}

        {(exec.confidence_note || exec.what_meta_adds) && (
          <div
            className="mt-5 pt-4 space-y-2 text-[13px]"
            style={{ borderTop: "1px solid var(--border)" }}
          >
            {exec.confidence_note && (
              <div>
                <span className="muted font-medium">Уверенность: </span>
                <span>{exec.confidence_note}</span>
              </div>
            )}
            {exec.what_meta_adds && (
              <div>
                <span className="muted font-medium">Что добавляет мета: </span>
                <span>{exec.what_meta_adds}</span>
              </div>
            )}
          </div>
        )}
      </section>

      {/* Main synthesis as markdown */}
      {report.main_synthesis && (
        <section className="card" style={{ padding: "1.5rem" }}>
          <h2 className="font-serif text-lg font-semibold tracking-tight mb-3">
            Синтез
          </h2>
          <MarkdownBlock text={report.main_synthesis} />
        </section>
      )}

      {/* Consensus / conflicts / gaps */}
      <div className="grid gap-4 md:grid-cols-3">
        <TextCard title="Консенсус" text={report.consensus_section} accent="emerald" />
        <TextCard title="Конфликты" text={report.conflicts_section} accent="rose" />
        <TextCard title="Gaps closed" text={report.gaps_filled_section} accent="amber" />
      </div>

      {/* Sources */}
      {report.all_sources.length > 0 && (
        <section className="card" style={{ padding: "1.5rem" }}>
          <h2 className="font-serif text-lg font-semibold tracking-tight mb-3">
            Источники ({report.all_sources.length})
          </h2>
          <div className="space-y-1.5">
            {report.all_sources.map((s, i) => (
              <a
                key={i}
                href={s.url}
                target="_blank"
                rel="noreferrer"
                className="flex items-start gap-2 text-sm group hover:text-blue-600 transition-colors"
              >
                <ExternalLink size={12} className="mt-1 flex-shrink-0 muted group-hover:text-blue-600" />
                <div className="min-w-0 flex-1">
                  <div className="truncate">{s.title || s.url}</div>
                  <div className="text-[11px] muted truncate font-mono">
                    {s.origin ? `[${s.origin}] ` : ""}{s.url}
                  </div>
                </div>
              </a>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function TextCard({
  title,
  text,
  accent,
}: {
  title: string;
  text: string;
  accent: "emerald" | "rose" | "amber";
}) {
  const bar: Record<string, string> = {
    emerald: "bg-emerald-400",
    rose: "bg-rose-400",
    amber: "bg-amber-400",
  };
  if (!text) return null;
  return (
    <section className="card overflow-hidden" style={{ padding: "1.25rem" }}>
      <div className={`h-0.5 w-10 mb-3 rounded-full ${bar[accent]}`} />
      <h3 className="text-sm font-semibold mb-2">{title}</h3>
      <MarkdownBlock text={text} />
    </section>
  );
}

// Lightweight markdown: ## headings, **bold**, *italic*, bullet lists, paragraphs.
export function MarkdownBlock({ text }: { text: string }) {
  const nodes = parseMarkdown(text);
  return <div className="text-sm leading-relaxed space-y-3">{nodes}</div>;
}

function parseMarkdown(text: string): React.ReactNode[] {
  const lines = text.split("\n");
  const out: React.ReactNode[] = [];
  let list: string[] = [];

  const flushList = () => {
    if (list.length) {
      out.push(
        <ul key={`ul-${out.length}`} className="list-disc pl-5 space-y-1">
          {list.map((li, i) => (
            <li key={i}>{inline(li)}</li>
          ))}
        </ul>
      );
      list = [];
    }
  };

  for (const raw of lines) {
    const line = raw.trimEnd();
    if (!line.trim()) {
      flushList();
      continue;
    }
    if (line.startsWith("## ")) {
      flushList();
      out.push(
        <h3 key={`h-${out.length}`} className="font-serif text-base font-semibold mt-2">
          {line.slice(3)}
        </h3>
      );
      continue;
    }
    if (line.startsWith("# ")) {
      flushList();
      out.push(
        <h2 key={`h-${out.length}`} className="font-serif text-lg font-semibold mt-2">
          {line.slice(2)}
        </h2>
      );
      continue;
    }
    if (/^\s*[-*]\s+/.test(line)) {
      list.push(line.replace(/^\s*[-*]\s+/, ""));
      continue;
    }
    flushList();
    out.push(
      <p key={`p-${out.length}`} className="leading-relaxed">
        {inline(line)}
      </p>
    );
  }
  flushList();
  return out;
}

function inline(s: string): React.ReactNode {
  // naive **bold** and *italic*
  const parts: React.ReactNode[] = [];
  const re = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let idx = 0;
  while ((m = re.exec(s)) !== null) {
    if (m.index > last) parts.push(s.slice(last, m.index));
    const tok = m[0];
    if (tok.startsWith("**")) {
      parts.push(<strong key={idx++}>{tok.slice(2, -2)}</strong>);
    } else if (tok.startsWith("`")) {
      parts.push(
        <code
          key={idx++}
          className="px-1 py-0.5 rounded bg-zinc-100 text-zinc-800 text-[12px] font-mono"
        >
          {tok.slice(1, -1)}
        </code>
      );
    } else {
      parts.push(<em key={idx++}>{tok.slice(1, -1)}</em>);
    }
    last = m.index + tok.length;
  }
  if (last < s.length) parts.push(s.slice(last));
  return parts;
}
