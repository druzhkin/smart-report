"use client";

import { useMemo, useState } from "react";
import type { Block } from "@/lib/api";

export function DeepenForm({
  block,
  onSubmit,
  onClose,
}: {
  block: Block;
  onSubmit: (focus: string) => Promise<void>;
  onClose: () => void;
}) {
  const suggestions = useMemo(() => block.gaps.slice(0, 4), [block]);
  const [focus, setFocus] = useState(suggestions[0] || "");
  const [opts, setOpts] = useState<{ n: boolean; c: boolean; i: boolean }>({
    n: false,
    c: false,
    i: false,
  });
  const [busy, setBusy] = useState(false);

  async function submit() {
    if (!focus.trim()) return;
    const parts = [focus.trim()];
    if (opts.n) parts.push("Добавь конкретные цифры с первичными источниками.");
    if (opts.c) parts.push("Найди противоположную точку зрения, контраргументы.");
    if (opts.i) parts.push("Добавь международный опыт и сравнительные кейсы.");
    setBusy(true);
    try {
      await onSubmit(parts.join(" "));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="p-4 space-y-3 text-sm">
      {suggestions.length > 0 && (
        <div className="flex gap-1 flex-wrap">
          {suggestions.map((s, i) => (
            <button
              key={i}
              type="button"
              className="btn text-xs"
              onClick={() => setFocus(s)}
            >
              {s.length > 70 ? s.slice(0, 67) + "…" : s}
            </button>
          ))}
        </div>
      )}
      <textarea
        rows={2}
        value={focus}
        onChange={(e) => setFocus(e.target.value)}
        placeholder="Фокус: что именно искать?"
      />
      <div className="flex gap-3 flex-wrap text-xs">
        <label className="flex gap-1 items-center">
          <input
            type="checkbox"
            className="!w-auto"
            checked={opts.n}
            onChange={(e) => setOpts((o) => ({ ...o, n: e.target.checked }))}
          />{" "}
          Добавить конкретные цифры
        </label>
        <label className="flex gap-1 items-center">
          <input
            type="checkbox"
            className="!w-auto"
            checked={opts.c}
            onChange={(e) => setOpts((o) => ({ ...o, c: e.target.checked }))}
          />{" "}
          Противоположная точка зрения
        </label>
        <label className="flex gap-1 items-center">
          <input
            type="checkbox"
            className="!w-auto"
            checked={opts.i}
            onChange={(e) => setOpts((o) => ({ ...o, i: e.target.checked }))}
          />{" "}
          Международный опыт
        </label>
      </div>
      <div className="flex gap-2">
        <button className="btn btn-primary" disabled={busy} onClick={submit}>
          {busy ? "Запускаю…" : "Запустить"}
        </button>
        <button className="btn" onClick={onClose}>Отмена</button>
      </div>
    </div>
  );
}
