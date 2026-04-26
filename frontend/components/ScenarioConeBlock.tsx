"use client";

import type { ScenarioCone, ScenarioItem } from "@/lib/api";

// Colour accent per scenario name
function accentClasses(name: string): { border: string; badge: string; prob: string } {
  const n = name.toLowerCase();
  if (n.includes("optim") || n.includes("оптим")) {
    return {
      border: "border-green-400",
      badge: "bg-green-50 text-green-700 border border-green-200",
      prob: "text-green-700",
    };
  }
  if (n.includes("pessim") || n.includes("пессим")) {
    return {
      border: "border-red-400",
      badge: "bg-red-50 text-red-700 border border-red-200",
      prob: "text-red-700",
    };
  }
  // Base case / default
  return {
    border: "border-blue-400",
    badge: "bg-blue-50 text-blue-700 border border-blue-200",
    prob: "text-blue-700",
  };
}

function ScenarioCard({ s }: { s: ScenarioItem }) {
  const cls = accentClasses(s.name);
  return (
    <div className={`rounded-lg border-2 ${cls.border} bg-white p-4 flex flex-col gap-3`}>
      <div className="flex items-start justify-between gap-2">
        <span className={`text-xs font-semibold px-2 py-0.5 rounded ${cls.badge}`}>
          {s.name}
        </span>
        <span className={`text-lg font-bold tabular-nums ${cls.prob}`}>{s.probability}</span>
      </div>

      <p className="text-sm leading-relaxed text-zinc-700">{s.description}</p>

      <div>
        <div className="text-xs font-semibold text-zinc-500 uppercase tracking-wide mb-1">
          Ключевой драйвер
        </div>
        <p className="text-sm text-zinc-800">{s.key_driver}</p>
      </div>

      {s.implications.length > 0 && (
        <div>
          <div className="text-xs font-semibold text-zinc-500 uppercase tracking-wide mb-1">
            Следствия для клиента
          </div>
          <ul className="space-y-1">
            {s.implications.map((imp, i) => (
              <li key={i} className="text-xs text-zinc-700 flex gap-1.5">
                <span className="text-zinc-400 mt-0.5">›</span>
                <span>{imp}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {s.indicators.length > 0 && (
        <div>
          <div className="text-xs font-semibold text-zinc-500 uppercase tracking-wide mb-1">
            Индикаторы (I&amp;W)
          </div>
          <ul className="space-y-1">
            {s.indicators.map((ind, i) => (
              <li key={i} className="text-xs text-zinc-600 flex gap-1.5">
                <span className="text-zinc-300 mt-0.5">◎</span>
                <span>{ind}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export function ScenarioConeBlock({ data }: { data: ScenarioCone }) {
  const horizon = data.question_horizon ?? "12-24 месяцев";

  return (
    <section id="sec-scenarios" className="not-italic font-sans">
      <div className="section-eyebrow mb-3">Конус сценариев · горизонт {horizon}</div>

      {data.conditional_verdict && (
        <blockquote className="border-l-4 border-blue-400 pl-4 py-2 bg-blue-50 rounded-r text-sm text-blue-900 leading-relaxed mb-4 italic">
          {data.conditional_verdict}
        </blockquote>
      )}

      {data.key_uncertainties && data.key_uncertainties.length > 0 && (
        <p className="text-xs text-zinc-500 mb-4">
          <span className="font-semibold text-zinc-600">Ключевые неопределённости: </span>
          {data.key_uncertainties.join(" · ")}
        </p>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
        {data.scenarios.map((s, i) => (
          <ScenarioCard key={i} s={s} />
        ))}
      </div>

      {data.wild_card && (
        <div className="border-2 border-dashed border-amber-400 rounded-lg p-4 bg-amber-50">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-xs font-bold text-amber-700 uppercase tracking-wide">
              Wild Card
            </span>
            <span className="text-xs font-bold text-amber-600 bg-amber-100 border border-amber-300 px-2 py-0.5 rounded">
              {data.wild_card.probability}
            </span>
          </div>
          <p className="text-sm text-amber-900 mb-1">{data.wild_card.description}</p>
          <p className="text-xs text-amber-700">
            <span className="font-semibold">Эффект: </span>
            {data.wild_card.impact}
          </p>
        </div>
      )}
    </section>
  );
}
