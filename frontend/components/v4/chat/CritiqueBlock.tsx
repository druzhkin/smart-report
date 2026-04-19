"use client";

/**
 * CritiqueBlock — assistant-side card for AnalysisOutput.
 *
 * Layout (top-down, restrained):
 *   one-line summary (N sources · M conflicts · K gaps · U unverified)
 *   muted quality_notes as pull-quote
 *   four collapsed sections: Противоречия / Пробелы / Согласия / Неподтверждённые
 *   followup prompt as <pre> with copy
 *   three stats row IS the first line — no 56pt giant numbers
 */

import { useState } from "react";
import type {
  AnalysisOutput,
  Conflict,
  Gap,
  ConsensusClaim,
  UnverifiedNumber,
  FollowupPrompt,
} from "@/lib/apiV4";
import { ChevronDown, ChevronRight, Copy, Check, ArrowRight } from "lucide-react";

export function CritiqueBlock({
  analysis,
  sourceCount,
  onContinue,
}: {
  analysis: AnalysisOutput;
  sourceCount: number;
  onContinue: () => void;
}) {
  // v4.1+: prefer single consolidated followup; fall back to first MUST
  // from legacy followup_prompts[] so readers stay happy during rollout.
  const followup: FollowupPrompt | null =
    analysis.followup_prompt ??
    analysis.followup_prompts.find((f) => f.priority === "must") ??
    analysis.followup_prompts[0] ??
    null;

  const stats = [
    { label: "отчётов", value: sourceCount },
    { label: "согласий", value: analysis.consensus.length },
    { label: "противоречий", value: analysis.conflicts.length },
    { label: "пробелов", value: analysis.gaps.length },
  ];

  return (
    <div
      className="vc-reveal"
      style={{ display: "flex", flexDirection: "column", gap: 20 }}
    >
      {/* Headline bubble + stats */}
      <div
        className="vc-bubble vc-bubble-assistant"
        style={{ padding: "20px 22px", display: "flex", flexDirection: "column", gap: 16 }}
      >
        <div style={{ fontSize: 15, lineHeight: 1.55 }}>
          Разобрал {sourceCount} {pluralRu(sourceCount, ["отчёт", "отчёта", "отчётов"])}.
          Нашёл {analysis.conflicts.length}{" "}
          {pluralRu(analysis.conflicts.length, ["противоречие", "противоречия", "противоречий"])},{" "}
          {analysis.gaps.length}{" "}
          {pluralRu(analysis.gaps.length, ["пробел", "пробела", "пробелов"])} и{" "}
          {analysis.unverified_numbers.length}{" "}
          {pluralRu(analysis.unverified_numbers.length, [
            "сомнительную цифру",
            "сомнительные цифры",
            "сомнительных цифр",
          ])}
          .
        </div>

        {/* Compact stats row — no 56pt giants */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(4, 1fr)",
            gap: 0,
          }}
        >
          {stats.map((s, i) => (
            <div
              key={s.label}
              style={{
                padding: "8px 12px 8px 12px",
                borderLeft:
                  i === 0 ? "none" : "1px solid var(--vc-border)",
                paddingLeft: i === 0 ? 0 : 14,
              }}
            >
              <div
                style={{
                  fontSize: 22,
                  fontWeight: 600,
                  lineHeight: 1,
                  letterSpacing: "-0.02em",
                  color: "var(--vc-text)",
                }}
              >
                {s.value}
              </div>
              <div
                className="vc-mono"
                style={{ fontSize: 11, marginTop: 4 }}
              >
                {s.label}
              </div>
            </div>
          ))}
        </div>

        {/* Quality notes as understated pull-quote */}
        {analysis.quality_notes && (
          <p
            style={{
              margin: 0,
              padding: "12px 16px",
              borderLeft: "2px solid var(--vc-border-s)",
              fontSize: 14,
              lineHeight: 1.6,
              color: "var(--vc-muted)",
              background: "var(--vc-surface-2)",
              borderRadius: "0 8px 8px 0",
            }}
          >
            {analysis.quality_notes}
          </p>
        )}
      </div>

      {/* Collapsible sections — all closed by default */}
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        <CollapsibleSection
          label="Противоречия"
          count={analysis.conflicts.length}
          defaultOpen={false}
        >
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            {analysis.conflicts.map((c, i) => (
              <ConflictItem key={i} c={c} />
            ))}
            {analysis.conflicts.length === 0 && <EmptyLine text="Источники не расходятся." />}
          </div>
        </CollapsibleSection>

        <CollapsibleSection
          label="Пробелы"
          count={analysis.gaps.length}
          defaultOpen={false}
        >
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            {analysis.gaps.map((g, i) => (
              <GapItem key={i} g={g} />
            ))}
            {analysis.gaps.length === 0 && <EmptyLine text="Критических пробелов нет." />}
          </div>
        </CollapsibleSection>

        <CollapsibleSection
          label="Согласия"
          count={analysis.consensus.length}
          defaultOpen={false}
        >
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {analysis.consensus.map((c, i) => (
              <ConsensusItem key={i} c={c} />
            ))}
            {analysis.consensus.length === 0 && <EmptyLine text="Общих утверждений не нашлось." />}
          </div>
        </CollapsibleSection>

        <CollapsibleSection
          label="Неподтверждённые цифры"
          count={analysis.unverified_numbers.length}
          defaultOpen={false}
        >
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {analysis.unverified_numbers.map((u, i) => (
              <UnverifiedItem key={i} u={u} />
            ))}
            {analysis.unverified_numbers.length === 0 && (
              <EmptyLine text="Сомнительных цифр нет." />
            )}
          </div>
        </CollapsibleSection>
      </div>

      {/* Followup prompt */}
      {followup && <FollowupCard fp={followup} />}

      {/* CTA */}
      <div>
        <button type="button" className="vc-btn vc-btn-primary" onClick={onContinue}>
          <span>Дальше — загрузить добор или сразу синтез</span>
          <ArrowRight size={14} strokeWidth={2} />
        </button>
      </div>
    </div>
  );
}

/* --------------- Section wrapper --------------- */

function CollapsibleSection({
  label,
  count,
  defaultOpen = false,
  children,
}: {
  label: string;
  count: number;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div
      style={{
        background: "var(--vc-surface)",
        border: "1px solid var(--vc-border)",
        borderRadius: 12,
        overflow: "hidden",
      }}
    >
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        style={{
          width: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "12px 16px",
          border: "none",
          background: "transparent",
          cursor: "pointer",
          fontFamily: "inherit",
          color: "var(--vc-text)",
          fontSize: 14,
          fontWeight: 500,
        }}
      >
        <span style={{ display: "inline-flex", alignItems: "center", gap: 10 }}>
          {open ? (
            <ChevronDown size={14} strokeWidth={1.75} style={{ color: "var(--vc-muted)" }} />
          ) : (
            <ChevronRight size={14} strokeWidth={1.75} style={{ color: "var(--vc-muted)" }} />
          )}
          {label}
        </span>
        <span className="vc-mono">{count}</span>
      </button>
      {open && (
        <div
          className="vc-reveal"
          style={{
            padding: "6px 16px 18px",
            borderTop: "1px solid var(--vc-border)",
          }}
        >
          {children}
        </div>
      )}
    </div>
  );
}

function EmptyLine({ text }: { text: string }) {
  return (
    <div style={{ fontSize: 13, color: "var(--vc-subtle)", paddingTop: 8 }}>
      {text}
    </div>
  );
}

/* --------------- Items --------------- */

function ConflictItem({ c }: { c: Conflict }) {
  const tone =
    c.importance === "critical" ? "var(--vc-text)" : "var(--vc-muted)";
  return (
    <article
      style={{
        padding: "14px 16px",
        background: "var(--vc-surface-2)",
        borderRadius: 10,
        display: "flex",
        flexDirection: "column",
        gap: 10,
      }}
    >
      <div style={{ display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
        <div style={{ fontSize: 14, fontWeight: 600, color: "var(--vc-text)" }}>{c.topic}</div>
        <span className="vc-chip" style={{ color: tone }}>
          {c.importance}
        </span>
      </div>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 12,
        }}
      >
        {[
          { src: c.source_a, text: c.claim_a },
          { src: c.source_b, text: c.claim_b },
        ].map((side, j) => (
          <div key={j}>
            <div className="vc-mono" style={{ fontSize: 10, marginBottom: 4 }}>
              {side.src}
            </div>
            <p style={{ margin: 0, fontSize: 13, lineHeight: 1.55, color: "var(--vc-text)" }}>
              {side.text}
            </p>
          </div>
        ))}
      </div>
      {c.resolution_hint && (
        <div
          style={{
            paddingTop: 8,
            borderTop: "1px solid var(--vc-border)",
            fontSize: 13,
            lineHeight: 1.55,
            color: "var(--vc-muted)",
          }}
        >
          <span className="vc-mono" style={{ fontSize: 10, marginRight: 6 }}>
            резолюция
          </span>
          {c.resolution_hint}
        </div>
      )}
    </article>
  );
}

function GapItem({ g }: { g: Gap }) {
  return (
    <article
      style={{
        padding: "12px 14px",
        background: "var(--vc-surface-2)",
        borderRadius: 10,
      }}
    >
      <div style={{ fontSize: 14, fontWeight: 600, color: "var(--vc-text)" }}>{g.topic}</div>
      <p
        style={{
          margin: "6px 0 0",
          fontSize: 13,
          lineHeight: 1.55,
          color: "var(--vc-muted)",
        }}
      >
        {g.why_critical}
      </p>
      {g.what_to_find && (
        <p
          style={{
            margin: "6px 0 0",
            fontSize: 13,
            lineHeight: 1.55,
            color: "var(--vc-text)",
          }}
        >
          <span className="vc-mono" style={{ fontSize: 10, marginRight: 6 }}>
            найти
          </span>
          {g.what_to_find}
        </p>
      )}
      {g.candidate_sources.length > 0 && (
        <div style={{ marginTop: 8, display: "flex", gap: 6, flexWrap: "wrap" }}>
          {g.candidate_sources.map((s, i) => (
            <span key={i} className="vc-chip">
              {s}
            </span>
          ))}
        </div>
      )}
    </article>
  );
}

function ConsensusItem({ c }: { c: ConsensusClaim }) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "1fr auto",
        gap: 12,
        padding: "10px 14px",
        background: "var(--vc-surface-2)",
        borderRadius: 10,
        alignItems: "center",
      }}
    >
      <p style={{ margin: 0, fontSize: 13, lineHeight: 1.55 }}>{c.claim}</p>
      <span className="vc-chip">{c.confidence}</span>
    </div>
  );
}

function UnverifiedItem({ u }: { u: UnverifiedNumber }) {
  return (
    <div
      style={{
        padding: "10px 14px",
        background: "var(--vc-surface-2)",
        borderRadius: 10,
      }}
    >
      <div style={{ display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
        <span
          style={{
            fontFamily: "var(--vc-f-mono)",
            fontVariantNumeric: "tabular-nums",
            fontWeight: 600,
            fontSize: 14,
            color: "var(--vc-text)",
          }}
        >
          {u.value}
        </span>
        <span style={{ fontSize: 13, color: "var(--vc-text)" }}>{u.metric}</span>
        {u.subject && <span className="vc-chip">{u.subject}</span>}
        <span className="vc-chip">{u.source_tool}</span>
      </div>
      <p style={{ margin: "6px 0 0", fontSize: 12, lineHeight: 1.5, color: "var(--vc-muted)" }}>
        {u.why_unverified}
      </p>
    </div>
  );
}

/* --------------- Followup card --------------- */

function FollowupCard({ fp }: { fp: FollowupPrompt }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(fp.prompt);
      setCopied(true);
      setTimeout(() => setCopied(false), 1400);
    } catch {
      /* ignore */
    }
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          paddingLeft: 4,
        }}
      >
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <span className="vc-mono" style={{ fontSize: 11 }}>
            followup-prompt
          </span>
          <span className="vc-chip">{fp.suggested_tool}</span>
          {fp.suggested_source_site && <span className="vc-chip">{fp.suggested_source_site}</span>}
        </div>
        <button
          type="button"
          className="vc-btn vc-btn-ghost vc-btn-sm"
          onClick={copy}
          aria-label="Скопировать followup"
        >
          {copied ? (
            <>
              <Check size={13} strokeWidth={2} /> <span>Скопировано</span>
            </>
          ) : (
            <>
              <Copy size={13} strokeWidth={1.75} /> <span>Копировать</span>
            </>
          )}
        </button>
      </div>
      <pre className="vc-code" style={{ margin: 0 }}>
        {fp.prompt}
      </pre>
      <p style={{ margin: 0, fontSize: 12, color: "var(--vc-muted)", lineHeight: 1.5 }}>
        Запустите в {fp.suggested_tool} — один заход закроет{" "}
        {fp.target_info || "все открытые вопросы"}. Затем загрузите файл ответа
        сюда, либо пропустите — синтез соберётся и без добора.
      </p>
    </div>
  );
}

/* --------------- utils --------------- */

function pluralRu(n: number, forms: [string, string, string]): string {
  const m10 = n % 10;
  const m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return forms[0];
  if (m10 >= 2 && m10 <= 4 && (m100 < 10 || m100 >= 20)) return forms[1];
  return forms[2];
}
