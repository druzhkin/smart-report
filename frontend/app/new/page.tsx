"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { startResearch } from "@/lib/api";

export default function NewRequestPage() {
  const router = useRouter();
  const [goal, setGoal] = useState("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit() {
    if (!goal.trim()) return;
    setLoading(true);
    setErr(null);
    try {
      const { id } = await startResearch(goal.trim());
      router.push(`/report/${id}`);
    } catch (e: any) {
      setErr(e?.message || "Failed");
      setLoading(false);
    }
  }

  return (
    <div className="max-w-2xl mx-auto space-y-5 pt-8">
      <h1 className="text-2xl font-semibold">Новый запрос</h1>
      <p className="muted text-sm">
        Сформулируй цель — одним предложением, конкретно. Примеры ниже.
      </p>
      <textarea
        rows={5}
        placeholder="Например: какие мировые тренды 2025–2030 повлияют на жилое строительство в России — технологические, демографические, экономические, культурные, экологические"
        value={goal}
        onChange={(e) => setGoal(e.target.value)}
      />
      <div className="flex flex-wrap gap-2 text-xs muted">
        {[
          "За что реально готовы платить покупатели квартир бизнес и премиум класса в Москве",
          "Как сделать сильный глубокий аналитический движок",
          "Как ИИ изменит персональную медицину в ближайшие 5 лет",
        ].map((s) => (
          <button key={s} className="btn" onClick={() => setGoal(s)}>
            {s.slice(0, 60)}…
          </button>
        ))}
      </div>
      {err && <div className="text-sm text-red-600">{err}</div>}
      <div>
        <button className="btn btn-primary" onClick={submit} disabled={loading}>
          {loading ? "Запускаю…" : "Запустить исследование"}
        </button>
      </div>
    </div>
  );
}
