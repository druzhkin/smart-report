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

export function renderWithCites(text: string, openSource: (n: number) => void): ReactNode {
  const parts = text.split(/(\[\d+\])/g);
  return parts.map((part, i) => {
    const m = part.match(/\[(\d+)\]/);
    if (m) return <Cite key={i} n={+m[1]} openSource={openSource} />;
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
  const [log, setLog] = useState<Array<{ step: string; dur: string }>>([]);

  useEffect(() => {
    if (idx >= traces.length - 1) {
      if (onDone) {
        const t = setTimeout(onDone, duration);
        return () => clearTimeout(t);
      }
      return;
    }
    const t = setTimeout(() => {
      setLog((l) => [
        ...l,
        { step: traces[idx], dur: (Math.random() * 1.6 + 0.4).toFixed(1) },
      ]);
      setIdx((i) => Math.min(i + 1, traces.length - 1));
    }, duration);
    return () => clearTimeout(t);
  }, [idx, traces.length, duration, onDone]);

  if (open) {
    return (
      <div className="thinking-collapsible">
        <div className="thinking-head" onClick={() => setOpen(false)}>
          <span>
            ↑ обрабатываю · {idx + 1} из {traces.length}
          </span>
          <span>свернуть</span>
        </div>
        <div className="thinking-log">
          {log.map((l, i) => (
            <div key={i} className="thinking-log-step">
              <span className="tick">✓</span>
              <span>{l.step}</span>
              <span className="dur">{l.dur}s</span>
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
