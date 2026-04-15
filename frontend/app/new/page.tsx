"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { startResearch } from "@/lib/api";
import { Paperclip, Play, Check } from "lucide-react";

type Depth = "light" | "standard" | "deep" | "exhaustive";

const DEPTHS: { id: Depth; title: string; hint: string }[] = [
  { id: "light", title: "Light", hint: "Быстрое резюме • ~2 мин" },
  { id: "standard", title: "Standard", hint: "Широкие источники • ~5 мин" },
  { id: "deep", title: "Deep", hint: "Академический фокус • ~12 мин" },
  { id: "exhaustive", title: "Exhaustive", hint: "Полный синтез • 20+ мин" },
];

const EXAMPLES = [
  "За что реально готовы платить покупатели квартир бизнес и премиум класса в Москве",
  "Как сделать сильный глубокий аналитический движок",
  "Как ИИ изменит персональную медицину в ближайшие 5 лет",
];

export default function NewRequestPage() {
  const router = useRouter();
  const [goal, setGoal] = useState("");
  const [depth, setDepth] = useState<Depth>("standard");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit() {
    if (!goal.trim()) return;
    setLoading(true);
    setErr(null);
    try {
      const { id } = await startResearch(goal.trim(), depth);
      router.push(`/report/${id}`);
    } catch (e: any) {
      setErr(e?.message || "Не удалось запустить");
      setLoading(false);
    }
  }

  function onKey(e: React.KeyboardEvent) {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") submit();
  }

  return (
    <div className="max-w-3xl mx-auto space-y-8">
      <section
        className="card relative overflow-hidden"
        style={{ padding: "2rem", boxShadow: "0 8px 30px rgb(0 0 0 / 0.04)" }}
      >
        <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-blue-400 via-indigo-500 to-purple-400 opacity-40" />

        <h2 className="font-serif text-2xl font-semibold tracking-tight mb-1">Новое исследование</h2>
        <p className="text-sm muted mb-6">
          Сформулируй цель одним предложением — конкретно. Выбери глубину и запускай.
        </p>

        <div className="space-y-6">
          <div className="relative">
            <label htmlFor="query" className="sr-only">Цель исследования</label>
            <textarea
              id="query"
              rows={4}
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
              onKeyDown={onKey}
              placeholder="Например: как ИИ изменит персональную медицину в ближайшие 5 лет, включая регуляторные барьеры"
              className="pb-10 resize-none"
              style={{ fontSize: "15px" }}
            />
            <div className="absolute bottom-3 right-3 flex items-center gap-3 text-xs muted pointer-events-none select-none">
              <span>{goal.length} / 500</span>
              <div className="flex items-center gap-1 opacity-70">
                <kbd
                  className="px-1.5 py-0.5 rounded-md font-medium text-[10px]"
                  style={{ background: "color-mix(in srgb, var(--border) 60%, transparent)", border: "1px solid var(--border)" }}
                >⌘</kbd>
                <kbd
                  className="px-1.5 py-0.5 rounded-md font-medium text-[10px]"
                  style={{ background: "color-mix(in srgb, var(--border) 60%, transparent)", border: "1px solid var(--border)" }}
                >Enter</kbd>
              </div>
            </div>
          </div>

          <div className="space-y-3">
            <span className="text-sm font-medium">Глубина</span>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
              {DEPTHS.map((d) => {
                const active = depth === d.id;
                return (
                  <button
                    key={d.id}
                    type="button"
                    onClick={() => setDepth(d.id)}
                    className="relative text-left rounded-lg p-4 transition-all active:scale-[0.98]"
                    style={{
                      background: "var(--card)",
                      border: active ? "1px solid var(--fg)" : "1px solid var(--border)",
                      boxShadow: active ? "0 0 0 1px var(--fg)" : "0 1px 2px rgb(0 0 0 / 0.04)",
                    }}
                  >
                    <div className="text-sm font-medium">{d.title}</div>
                    <div className="mt-1 text-xs muted">{d.hint}</div>
                    {active && (
                      <Check size={16} className="absolute top-3 right-3" style={{ color: "var(--fg)" }} />
                    )}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="flex flex-wrap gap-2">
            {EXAMPLES.map((s) => (
              <button
                key={s}
                type="button"
                className="btn text-xs"
                onClick={() => setGoal(s)}
                title={s}
              >
                {s.length > 60 ? s.slice(0, 60) + "…" : s}
              </button>
            ))}
          </div>

          {err && <div className="text-sm text-red-600">{err}</div>}

          <div className="flex items-center justify-between pt-4" style={{ borderTop: "1px solid var(--border)" }}>
            <button type="button" className="flex items-center gap-2 text-sm muted hover:opacity-80 transition-opacity" disabled title="Скоро">
              <Paperclip size={16} />
              Прикрепить контекст (PDF/TXT)
            </button>
            <button
              className="btn btn-primary"
              onClick={submit}
              disabled={loading || !goal.trim()}
              style={{ padding: "10px 20px" }}
            >
              <Play size={14} />
              {loading ? "Запускаю…" : "Запустить"}
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}
