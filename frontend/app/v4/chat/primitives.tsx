"use client";

// Smart Report v.IV — primitives (Msg, ArtifactRef, Thinking, Cite)

import { useState, useEffect, useRef, Fragment, ReactNode } from "react";

// ========== Cite ==========
interface CiteProps {
  n: number;
  openSource: (n: number) => void;
}
export function Cite({ n, openSource }: CiteProps) {
  return (
    <button className="cite" onClick={() => openSource(n)}>
      {n}
    </button>
  );
}

// Evidence-grade tag rendering. Synthesizer prompts the LLM to mark every
// claim with [STRONG] / [MODERATE] / [WEAK] / [SPECULATIVE] inline. Reading
// "[STRONG] По данным…" everywhere kills flow — replace with a small
// coloured dot at the start, and the original word becomes a tooltip.
const GRADE_STYLE: Record<string, { color: string; title: string }> = {
  STRONG: { color: "#16a34a", title: "STRONG: первичный источник (ЦБ, Росстат, peer-review)" },
  MODERATE: { color: "#2563eb", title: "MODERATE: авторитетный consultancy/industry report" },
  WEAK: { color: "#d97706", title: "WEAK: secondary analysis (РБК, Forbes, Коммерсантъ)" },
  SPECULATIVE: { color: "#dc2626", title: "SPECULATIVE: авторский синтез / экспертная оценка" },
};

export function renderWithCites(text: string, openSource: (n: number) => void): ReactNode {
  // Combined regex captures: numeric cite [N], grade-tag [STRONG|...].
  const parts = text.split(/(\[\d+\]|\[(?:STRONG|MODERATE|WEAK|SPECULATIVE)\])/g);
  return parts.map((part, i) => {
    const num = part.match(/^\[(\d+)\]$/);
    if (num) return <Cite key={i} n={+num[1]} openSource={openSource} />;
    const grade = part.match(/^\[(STRONG|MODERATE|WEAK|SPECULATIVE)\]$/);
    if (grade) {
      const g = GRADE_STYLE[grade[1]];
      return (
        <span
          key={i}
          title={g.title}
          aria-label={grade[1]}
          style={{
            display: "inline-block",
            width: 8,
            height: 8,
            borderRadius: "50%",
            backgroundColor: g.color,
            marginRight: 4,
            verticalAlign: "middle",
            cursor: "help",
          }}
        />
      );
    }
    return <Fragment key={i}>{part}</Fragment>;
  });
}

// ========== Msg wrapper ==========
interface MsgProps {
  role: "system" | "user";
  meta?: string;
  children: ReactNode;
  noAnim?: boolean;
}
export function Msg({ role, meta, children, noAnim }: MsgProps) {
  const avatar =
    role === "user" ? (
      <div className="msg-avatar user">ВЫ</div>
    ) : (
      <div className="msg-avatar system">SR</div>
    );
  return (
    <div className={`msg ${role}${noAnim ? " no-anim" : ""}`}>
      {avatar}
      <div className="msg-body">
        <div className="msg-text">{children}</div>
        {meta && <div className="msg-meta">{meta}</div>}
      </div>
    </div>
  );
}

// ========== Thinking collapsible log ==========
interface ThinkingProps {
  traces: string[];
  duration?: number;
  onDone?: () => void;
}
export function Thinking({ traces, duration = 2200, onDone }: ThinkingProps) {
  const [idx, setIdx] = useState(0);
  const [open, setOpen] = useState(false);
  const [log, setLog] = useState<string[]>([]);
  const [elapsed, setElapsed] = useState(0);
  const startedAt = useRef<number>(Date.now());

  // Real elapsed wall-clock timer (updates every second).
  useEffect(() => {
    startedAt.current = Date.now();
    const t = setInterval(() => {
      setElapsed(Math.floor((Date.now() - startedAt.current) / 1000));
    }, 1000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    if (idx >= traces.length - 1) {
      if (onDone) {
        const t = setTimeout(onDone, duration);
        return () => clearTimeout(t);
      }
      return;
    }
    const t = setTimeout(() => {
      setLog((l) => [...l, traces[idx]]);
      setIdx((i) => Math.min(i + 1, traces.length - 1));
    }, duration);
    return () => clearTimeout(t);
  }, [idx, traces.length, duration, onDone]);

  const elapsedLabel = elapsed < 60
    ? `${elapsed}с`
    : `${Math.floor(elapsed / 60)}м ${elapsed % 60}с`;

  if (open) {
    return (
      <div className="thinking-collapsible">
        <div className="thinking-head" onClick={() => setOpen(false)}>
          <span>
            ↑ обрабатываю · {idx + 1} из {traces.length} · {elapsedLabel}
          </span>
          <span>свернуть</span>
        </div>
        <div className="thinking-log">
          {log.map((step, i) => (
            <div key={i} className="thinking-log-step">
              <span className="tick">✓</span>
              <span>{step}</span>
            </div>
          ))}
          {idx < traces.length && (
            <div className="thinking-log-step">
              <span className="tick" style={{ color: "var(--accent)" }}>
                ›
              </span>
              <span>{traces[idx]}</span>
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div
      className="thinking"
      onClick={() => setOpen(true)}
      style={{ cursor: "pointer" }}
    >
      <span className="thinking-dots">
        <span></span>
        <span></span>
        <span></span>
      </span>
      <span className="thinking-trace">{traces[idx]}</span>
      <span
        style={{
          fontFamily: "var(--sans)",
          fontSize: 10,
          color: "var(--ink-4)",
          letterSpacing: "0.04em",
        }}
      >
        {idx + 1}/{traces.length}
      </span>
    </div>
  );
}

// ========== ArtifactRef (in-chat thumbnail) ==========
interface ArtifactRefProps {
  kind: string;
  title: string;
  subtitle: string;
  active?: boolean;
  onClick?: () => void;
  accent?: boolean;
}
export function ArtifactRef({
  kind,
  title,
  subtitle,
  active,
  onClick,
  accent,
}: ArtifactRefProps) {
  const marks: Record<string, string> = {
    prompt: "PR",
    upload: "UP",
    critique: "CR",
    report: "RP",
    topup: "TU",
  };
  return (
    <div
      className={"artifact-ref" + (active ? " active" : "")}
      onClick={onClick}
    >
      <div className={"artifact-ref-thumb" + (accent ? " accent" : "")}>
        {marks[kind] || "??"}
      </div>
      <div className="artifact-ref-body">
        <div className="artifact-ref-title">{title}</div>
        <div className="artifact-ref-sub">{subtitle}</div>
      </div>
      <div className="artifact-ref-arrow">›</div>
    </div>
  );
}
