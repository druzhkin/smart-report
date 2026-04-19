"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { getSession, synthesize, type V4Session, type AnalysisOutput, type Conflict, type Gap, type ConsensusClaim, type UnverifiedNumber, type FollowupPrompt } from "@/lib/apiV4";
import { useCost } from "@/lib/costContext";
import { LivePipeline } from "@/components/LivePipeline";
import { ProcessingOverlay } from "@/components/v4/ProcessingOverlay";
import { SectionKicker } from "@/components/v4/SectionKicker";
import { Collapsible } from "@/components/v4/Collapsible";
import { ToolMark } from "@/components/v4/ToolMark";
import { ToolBadge } from "@/components/v4/ToolBadge";
import { CopyButton } from "@/components/v4/CopyButton";
import { Icons } from "@/components/v4/Icon";

type UIEvent = { event: string; message: string };

export default function V4AnalysisPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = params?.id || "";
  const { setCost } = useCost();

  const [session, setSession] = useState<V4Session | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [synthesizing, setSynthesizing] = useState(false);
  const [events, setEvents] = useState<UIEvent[]>([]);
  const [doneMap, setDoneMap] = useState<Record<string, boolean>>({});

  useEffect(() => {
    if (!id) return;
    getSession(id)
      .then((s) => { setSession(s); setCost(s.total_cost_rub); })
      .catch((e) => setErr(e instanceof Error ? e.message : "Не удалось загрузить"));
  }, [id]);

  async function skipAndSynthesize() {
    if (synthesizing) return;
    setSynthesizing(true);
    setErr(null);
    setEvents([
      { event: "prompt_master", message: "Промт готов" },
      { event: "external_research", message: "Отчёты загружены" },
      { event: "analyzer", message: "Критика готова" },
      { event: "synthesizer", message: "Собираю финальный отчёт" },
    ]);
    try {
      await synthesize(id);
      router.push(`/v4/session/${id}/report`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Не удалось синтезировать");
      setSynthesizing(false);
    }
  }

  if (synthesizing) {
    return <ProcessingOverlay stage="synthesizer" />;
  }

  if (err) {
    return (
      <div className="v4-container" style={{ paddingTop: 48 }}>
        <div style={{ fontSize: 13, color: "#b91c1c" }}>{err}</div>
      </div>
    );
  }

  if (!session || !session.analysis) {
    return (
      <div className="v4-container" style={{ paddingTop: 48 }}>
        <div style={{ fontSize: 13, color: "var(--v4-ink-3)" }}>Загружаю критику…</div>
      </div>
    );
  }

  const a = session.analysis;
  const mustFollowups = a.followup_prompts.filter((f) => f.priority === "must");
  const niceFollowups = a.followup_prompts.filter((f) => f.priority === "nice");

  return (
    <div
      className="v4-container"
      style={{ paddingTop: 48, paddingBottom: 96, position: "relative", zIndex: 1 }}
    >
      {/* Breadcrumb */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 32 }}>
        <span className="v4-mono" style={{ color: "var(--v4-ink-4)" }}>Загрузка / </span>
        <span className="v4-mono">Критика</span>
        <span style={{ width: 16, height: 1, background: "var(--v4-rule-strong)" }} />
        <span className="v4-mono" style={{ color: "var(--v4-ink-4)" }}>Добор →</span>
      </div>

      {/* Hero summary */}
      <section style={{ marginBottom: 48 }}>
        <SectionKicker number="04">Разбор критика</SectionKicker>

        <div
          style={{
            marginTop: 18,
            paddingTop: 24,
            paddingBottom: 32,
            borderTop: "1px solid var(--v4-rule-emphatic)",
            borderBottom: "1px solid var(--v4-rule-emphatic)",
          }}
        >
          <h1 className="v4-display v4-display-xl" style={{ marginBottom: 24 }}>
            Мы нашли {a.conflicts.length} противоречий
            <br />и {a.gaps.length} критических пробела.
          </h1>

          {/* 4 big numbers */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(4, 1fr)",
              gap: 0,
              marginTop: 24,
            }}
          >
            {[
              { label: "Отчётов", value: session.source_reports.length, accent: false },
              { label: "Согласий", value: a.consensus.length, accent: false },
              { label: "Противоречий", value: a.conflicts.length, accent: true },
              { label: "Пробелов", value: a.gaps.length, accent: true },
            ].map((s, i) => (
              <div
                key={i}
                style={{
                  padding: "16px 24px 16px 0",
                  borderLeft: i === 0 ? "none" : "1px solid var(--v4-rule)",
                  paddingLeft: i === 0 ? 0 : 24,
                }}
              >
                <div className="v4-mono" style={{ fontSize: 10 }}>{s.label}</div>
                <div
                  style={{
                    fontFamily: "var(--v4-f-display)",
                    fontSize: 56,
                    lineHeight: 1,
                    marginTop: 6,
                    color: s.accent ? "var(--v4-accent)" : "var(--v4-ink)",
                  }}
                >
                  {s.value}
                </div>
              </div>
            ))}
          </div>

          {/* Quality notes */}
          {a.quality_notes && (
            <div
              style={{
                marginTop: 32,
                paddingTop: 20,
                borderTop: "1px solid var(--v4-rule)",
                display: "grid",
                gridTemplateColumns: "180px 1fr",
                gap: 32,
              }}
            >
              <div className="v4-mono">Заметка аналитика</div>
              <p
                style={{
                  fontFamily: "var(--v4-f-display)",
                  fontSize: 20,
                  lineHeight: 1.5,
                  color: "var(--v4-ink-2)",
                  margin: 0,
                  maxWidth: 780,
                }}
              >
                {a.quality_notes}
              </p>
            </div>
          )}
        </div>
      </section>

      {/* Collapsible sections */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: 0 }}>
        <Collapsible
          defaultOpen
          kicker="01 / наивысшая ценность"
          title="Противоречия"
          right={
            <span
              style={{
                fontFamily: "var(--v4-f-mono)",
                fontVariantNumeric: "tabular-nums",
                fontSize: 14,
                color: "var(--v4-ink-2)",
              }}
            >
              {a.conflicts.length}
            </span>
          }
        >
          <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
            {a.conflicts.map((c, i) => (
              <ConflictBlock key={i} c={c} idx={i + 1} />
            ))}
          </div>
        </Collapsible>

        <Collapsible
          defaultOpen
          kicker="02 / что не покрыто"
          title="Пробелы"
          right={
            <span
              style={{
                fontFamily: "var(--v4-f-mono)",
                fontVariantNumeric: "tabular-nums",
                fontSize: 14,
                color: "var(--v4-ink-2)",
              }}
            >
              {a.gaps.length}
            </span>
          }
        >
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(2, 1fr)",
              gap: 0,
            }}
          >
            {a.gaps.map((g, i) => (
              <GapBlock key={i} g={g} idx={i} />
            ))}
          </div>
        </Collapsible>

        <Collapsible
          kicker="03 / база"
          title="Согласия"
          right={
            <span
              style={{
                fontFamily: "var(--v4-f-mono)",
                fontVariantNumeric: "tabular-nums",
                fontSize: 14,
                color: "var(--v4-ink-2)",
              }}
            >
              {a.consensus.length}
            </span>
          }
        >
          <ConsensusBlock items={a.consensus} />
        </Collapsible>

        <Collapsible
          kicker="04 / осторожно"
          title="Неподтверждённые цифры"
          right={
            <span
              style={{
                fontFamily: "var(--v4-f-mono)",
                fontVariantNumeric: "tabular-nums",
                fontSize: 14,
                color: "var(--v4-ink-2)",
              }}
            >
              {a.unverified_numbers.length}
            </span>
          }
        >
          {a.unverified_numbers.map((u, i) => (
            <UnverifiedBlock key={i} u={u} idx={i} total={a.unverified_numbers.length} />
          ))}
        </Collapsible>
      </div>

      {/* Followups section */}
      <section style={{ marginTop: 72 }}>
        <div
          style={{
            borderTop: "1px solid var(--v4-rule-emphatic)",
            borderBottom: "1px solid var(--v4-rule-emphatic)",
            padding: "20px 0",
            marginBottom: 32,
            display: "flex",
            alignItems: "baseline",
            justifyContent: "space-between",
          }}
        >
          <div>
            <SectionKicker number="05">Добор</SectionKicker>
            <h2
              className="v4-display v4-display-l"
              style={{ marginTop: 10, marginBottom: 4 }}
            >
              Followup-промты
            </h2>
            <p style={{ color: "var(--v4-ink-3)", fontSize: 14, maxWidth: 560 }}>
              Запустите их в рекомендованных инструментах. Закройте пробелы, проверьте
              противоречия.
            </p>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
            <div style={{ textAlign: "right" }}>
              <div className="v4-mono">MUST</div>
              <div
                style={{
                  fontFamily: "var(--v4-f-mono)",
                  fontVariantNumeric: "tabular-nums",
                  fontSize: 24,
                  color: "var(--v4-ink)",
                }}
              >
                {mustFollowups.length}
              </div>
            </div>
            <div style={{ textAlign: "right" }}>
              <div className="v4-mono">NICE</div>
              <div
                style={{
                  fontFamily: "var(--v4-f-mono)",
                  fontVariantNumeric: "tabular-nums",
                  fontSize: 24,
                  color: "var(--v4-ink-3)",
                }}
              >
                {niceFollowups.length}
              </div>
            </div>
          </div>
        </div>

        {/* MUST */}
        {mustFollowups.length > 0 && (
          <div style={{ marginBottom: 40 }}>
            <SectionKicker>Обязательные</SectionKicker>
            <div style={{ marginTop: 18, display: "flex", flexDirection: "column", gap: 16 }}>
              {mustFollowups.map((f, i) => (
                <FollowupCard
                  key={f.prompt_id}
                  f={f}
                  idx={i + 1}
                  done={!!doneMap[f.prompt_id]}
                  onToggle={() =>
                    setDoneMap({ ...doneMap, [f.prompt_id]: !doneMap[f.prompt_id] })
                  }
                />
              ))}
            </div>
          </div>
        )}

        {/* NICE */}
        {niceFollowups.length > 0 && (
          <div style={{ opacity: 0.85 }}>
            <SectionKicker>По желанию</SectionKicker>
            <div style={{ marginTop: 18, display: "flex", flexDirection: "column", gap: 16 }}>
              {niceFollowups.map((f, i) => (
                <FollowupCard
                  key={f.prompt_id}
                  f={f}
                  idx={i + 1}
                  done={!!doneMap[f.prompt_id]}
                  onToggle={() =>
                    setDoneMap({ ...doneMap, [f.prompt_id]: !doneMap[f.prompt_id] })
                  }
                />
              ))}
            </div>
          </div>
        )}
      </section>

      {/* Bottom CTAs */}
      <div
        style={{
          marginTop: 72,
          paddingTop: 24,
          borderTop: "1px solid var(--v4-rule-emphatic)",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <button
          className="v4-btn v4-btn-ghost"
          onClick={() => router.push(`/v4/session/${id}/upload`)}
          style={{ fontSize: 13 }}
        >
          <Icons.arrowLeft /> Назад к загрузке
        </button>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <button className="v4-btn v4-btn-secondary" onClick={skipAndSynthesize}>
            Пропустить добор, собрать финал
          </button>
          <button
            className="v4-btn v4-btn-primary"
            onClick={() => router.push(`/v4/session/${id}/dobor`)}
          >
            Загрузить добор <Icons.arrowRight />
          </button>
        </div>
      </div>
    </div>
  );
}

function ConflictBlock({ c, idx }: { c: Conflict; idx: number }) {
  const isCritical = c.importance === "critical";
  return (
    <article
      style={{
        border: "1px solid var(--v4-rule)",
        background: "var(--v4-paper)",
        padding: 0,
      }}
    >
      <header
        style={{
          padding: "14px 20px",
          borderBottom: "1px solid var(--v4-rule)",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          background: isCritical ? "var(--v4-accent-wash)" : "var(--v4-paper-3)",
          color: isCritical ? "var(--v4-accent-ink)" : "var(--v4-ink)",
          borderLeft: isCritical ? "2px solid var(--v4-accent)" : "none",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <span
            style={{
              fontFamily: "var(--v4-f-mono)",
              fontVariantNumeric: "tabular-nums",
              fontSize: 11,
              opacity: 0.7,
            }}
          >
            CNF · {String(idx).padStart(2, "0")}
          </span>
          <span
            style={{
              fontFamily: "var(--v4-f-display)",
              fontSize: 22,
              fontWeight: 400,
            }}
          >
            {c.topic}
          </span>
        </div>
        <span
          className={`v4-badge ${isCritical ? "v4-badge-accent" : c.importance === "material" ? "" : ""}`}
        >
          {c.importance}
        </span>
      </header>

      {/* Two sides */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1px 1fr" }}>
        <ConflictSide label="A" tool={c.source_a} text={c.claim_a} />
        <div style={{ background: "var(--v4-rule)" }} />
        <ConflictSide label="B" tool={c.source_b} text={c.claim_b} />
      </div>

      {/* Resolution */}
      {c.resolution_hint && (
        <footer
          style={{
            borderTop: "1px solid var(--v4-rule)",
            padding: "16px 20px",
            background: "var(--v4-paper-3)",
            display: "grid",
            gridTemplateColumns: "140px 1fr",
            gap: 20,
            alignItems: "baseline",
          }}
        >
          <div className="v4-mono">Разрешение</div>
          <p style={{ fontSize: 14, lineHeight: 1.55, margin: 0, color: "var(--v4-ink-2)" }}>
            {c.resolution_hint}
          </p>
        </footer>
      )}
    </article>
  );
}

function ConflictSide({ label, tool, text }: { label: string; tool: string; text: string }) {
  return (
    <div style={{ padding: "20px 24px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12 }}>
        <span
          style={{
            fontFamily: "var(--v4-f-display)",
            fontSize: 30,
            lineHeight: 1,
            color: "var(--v4-ink-4)",
          }}
        >
          {label}
        </span>
        <ToolBadge tool={tool} small />
      </div>
      <p
        style={{
          fontSize: 15,
          lineHeight: 1.55,
          margin: 0,
          fontFamily: "var(--v4-f-display)",
          color: "var(--v4-ink)",
        }}
      >
        «{text}»
      </p>
    </div>
  );
}

function GapBlock({ g, idx }: { g: Gap; idx: number }) {
  return (
    <div
      style={{
        padding: "20px 24px",
        borderLeft: idx % 2 === 0 ? "none" : "1px solid var(--v4-rule)",
        borderTop: idx >= 2 ? "1px solid var(--v4-rule)" : "none",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
        <span className="v4-mono" style={{ fontSize: 10 }}>
          §{String(idx + 1).padStart(2, "0")}
        </span>
      </div>
      <h3
        style={{
          fontFamily: "var(--v4-f-display)",
          fontSize: 20,
          fontWeight: 400,
          marginBottom: 10,
          color: "var(--v4-ink)",
        }}
      >
        {g.topic}
      </h3>
      <p style={{ fontSize: 13, color: "var(--v4-ink-3)", lineHeight: 1.55, marginBottom: 10 }}>
        <strong style={{ color: "var(--v4-ink-2)" }}>Почему важно:</strong>{" "}
        {g.why_critical}
      </p>
      <p style={{ fontSize: 13, color: "var(--v4-ink-3)", lineHeight: 1.55, marginBottom: 10 }}>
        <strong style={{ color: "var(--v4-ink-2)" }}>Что искать:</strong>{" "}
        {g.what_to_find}
      </p>
      {g.candidate_sources.length > 0 && (
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginTop: 8 }}>
          <span className="v4-mono" style={{ fontSize: 9 }}>источники:</span>
          {g.candidate_sources.map((s, j) => (
            <span
              key={j}
              style={{
                fontFamily: "var(--v4-f-mono)",
                fontSize: 11,
                padding: "2px 6px",
                border: "1px solid var(--v4-rule-strong)",
                color: "var(--v4-ink-2)",
              }}
            >
              {s}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function ConsensusBlock({ items }: { items: ConsensusClaim[] }) {
  return (
    <div>
      {items.map((c, i) => (
        <div
          key={i}
          style={{
            display: "grid",
            gridTemplateColumns: "1fr auto auto",
            gap: 20,
            padding: "16px 0",
            borderTop: i === 0 ? "none" : "1px solid var(--v4-rule)",
            alignItems: "start",
          }}
        >
          <p style={{ fontSize: 14, lineHeight: 1.5, margin: 0, maxWidth: 760 }}>{c.claim}</p>
          <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
            {c.supporting_sources.map((s) => (
              <ToolMark key={s} tool={s} size={20} />
            ))}
          </div>
          <span
            className={`v4-badge ${c.confidence === "high" ? "v4-badge-ok" : ""}`}
          >
            {c.confidence}
          </span>
        </div>
      ))}
    </div>
  );
}

function UnverifiedBlock({
  u,
  idx,
  total,
}: {
  u: UnverifiedNumber;
  idx: number;
  total: number;
}) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "140px 1fr auto",
        gap: 20,
        padding: "16px 0",
        borderTop: idx === 0 ? "none" : "1px solid var(--v4-rule)",
        alignItems: "baseline",
      }}
    >
      <div
        style={{
          fontFamily: "var(--v4-f-display)",
          fontSize: 28,
          lineHeight: 1,
          color: "var(--v4-accent)",
        }}
      >
        {u.value}
      </div>
      <div>
        <div style={{ fontSize: 14, color: "var(--v4-ink)" }}>{u.metric}</div>
        <div style={{ fontSize: 12, color: "var(--v4-ink-3)", marginTop: 4 }}>
          {u.why_unverified}
        </div>
      </div>
      <ToolBadge tool={u.source_tool} small />
    </div>
  );
}

function FollowupCard({
  f,
  idx,
  done,
  onToggle,
}: {
  f: FollowupPrompt;
  idx: number;
  done: boolean;
  onToggle: () => void;
}) {
  return (
    <article
      style={{
        border: "1px solid var(--v4-rule)",
        background: done ? "var(--v4-paper-3)" : "var(--v4-paper-2)",
        opacity: done ? 0.55 : 1,
        display: "grid",
        gridTemplateColumns: "44px 1fr",
        alignItems: "stretch",
        transition: "all .2s",
      }}
    >
      {/* Check column */}
      <button
        onClick={onToggle}
        aria-label="Отметить как сделанное"
        style={{
          background: done ? "var(--v4-accent)" : "transparent",
          color: done ? "var(--v4-paper)" : "var(--v4-ink-3)",
          border: "none",
          borderRight: "1px solid var(--v4-rule)",
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        {done ? (
          <Icons.check />
        ) : (
          <span
            style={{
              fontFamily: "var(--v4-f-mono)",
              fontVariantNumeric: "tabular-nums",
              fontSize: 12,
            }}
          >
            {String(idx).padStart(2, "0")}
          </span>
        )}
      </button>

      <div style={{ padding: "16px 20px" }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: 10,
            flexWrap: "wrap",
            gap: 10,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
            <ToolBadge tool={f.suggested_tool} small />
            {f.suggested_source_site && (
              <span
                style={{
                  fontFamily: "var(--v4-f-mono)",
                  fontVariantNumeric: "tabular-nums",
                  fontSize: 11,
                  padding: "2px 6px",
                  border: "1px solid var(--v4-rule-strong)",
                  color: "var(--v4-ink-3)",
                }}
              >
                {f.suggested_source_site}
              </span>
            )}
            <span
              className={`v4-badge ${f.priority === "must" ? "v4-badge-ink" : ""}`}
              style={{ fontSize: 9 }}
            >
              {f.priority}
            </span>
          </div>
          <CopyButton text={f.prompt} label="Копировать" />
        </div>

        <h4
          style={{
            fontFamily: "var(--v4-f-display)",
            fontSize: 20,
            fontWeight: 400,
            lineHeight: 1.2,
            margin: "4px 0 10px",
            color: "var(--v4-ink)",
          }}
        >
          {f.target_info}
        </h4>
        <p
          style={{
            fontSize: 14,
            lineHeight: 1.55,
            color: "var(--v4-ink-2)",
            margin: 0,
            fontFamily: "var(--v4-f-body)",
          }}
        >
          {f.prompt}
        </p>
      </div>
    </article>
  );
}
