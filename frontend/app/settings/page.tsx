"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ThemeToggle } from "@/components/ThemeToggle";
import { Cpu, Database, KeyRound, Zap } from "lucide-react";

type Depth = "light" | "standard" | "deep" | "exhaustive";

const DEPTHS: { id: Depth; title: string; cost: string }[] = [
  { id: "light", title: "Light", cost: "~1 ₽" },
  { id: "standard", title: "Standard", cost: "~3 ₽" },
  { id: "deep", title: "Deep", cost: "~8 ₽" },
  { id: "exhaustive", title: "Exhaustive", cost: "~20 ₽" },
];

export default function SettingsPage() {
  const [defaultDepth, setDefaultDepth] = useState<Depth>("standard");
  const [health, setHealth] = useState<"checking" | "ok" | "down">("checking");

  useEffect(() => {
    try {
      const v = localStorage.getItem("default_depth") as Depth | null;
      if (v) setDefaultDepth(v);
    } catch {}
    fetch("/api/health")
      .then((r) => setHealth(r.ok ? "ok" : "down"))
      .catch(() => setHealth("down"));
  }, []);

  function pickDepth(d: Depth) {
    setDefaultDepth(d);
    try {
      localStorage.setItem("default_depth", d);
    } catch {}
  }

  return (
    <div className="max-w-3xl space-y-8">
      <div>
        <h1 className="text-2xl font-semibold">Настройки</h1>
        <p className="muted text-sm mt-1">Предпочтения отображения и поведения по умолчанию</p>
      </div>

      <section className="card p-5 space-y-4">
        <div className="flex items-center gap-2">
          <Zap size={16} className="text-zinc-500" />
          <h2 className="font-medium">Глубина по умолчанию</h2>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          {DEPTHS.map((d) => (
            <button
              key={d.id}
              onClick={() => pickDepth(d.id)}
              className={
                "card p-3 text-left transition-colors " +
                (defaultDepth === d.id
                  ? "border-zinc-900 dark:border-zinc-100"
                  : "hover:border-zinc-400")
              }
            >
              <div className="font-medium text-sm">{d.title}</div>
              <div className="muted text-xs mt-1">{d.cost}</div>
            </button>
          ))}
        </div>
        <p className="muted text-xs">
          На странице <Link href="/new" className="underline">Новый запрос</Link> будет выбрана эта глубина.
        </p>
      </section>

      <section className="card p-5 space-y-3">
        <div className="flex items-center gap-2">
          <Cpu size={16} className="text-zinc-500" />
          <h2 className="font-medium">Тема интерфейса</h2>
        </div>
        <ThemeToggle />
      </section>

      <section className="card p-5 space-y-3">
        <div className="flex items-center gap-2">
          <Database size={16} className="text-zinc-500" />
          <h2 className="font-medium">Статус сервиса</h2>
        </div>
        <div className="flex items-center gap-2 text-sm">
          <span
            className={
              "inline-block w-2 h-2 rounded-full " +
              (health === "ok"
                ? "bg-emerald-500"
                : health === "down"
                  ? "bg-red-500"
                  : "bg-zinc-400 animate-pulse")
            }
          />
          {health === "ok" && "Бэкенд доступен"}
          {health === "down" && "Бэкенд недоступен"}
          {health === "checking" && "Проверка…"}
        </div>
      </section>

      <section className="card p-5 space-y-3">
        <div className="flex items-center gap-2">
          <KeyRound size={16} className="text-zinc-500" />
          <h2 className="font-medium">О сервисе</h2>
        </div>
        <div className="text-sm muted space-y-1">
          <div>Smart Report MVP — глубокая кросс-доменная аналитика по одной цели.</div>
          <div>
            Пайплайн: planner → scouts → analysts → bisociator → summary. Источники: 8 академических API + Perplexity/Tavily для web.
          </div>
        </div>
      </section>
    </div>
  );
}
