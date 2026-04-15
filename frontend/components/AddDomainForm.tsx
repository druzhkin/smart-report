"use client";

import { useState } from "react";
import { motion } from "framer-motion";

export function AddDomainForm({
  onSubmit,
  onClose,
}: {
  onSubmit: (payload: { name?: string; layers?: string[]; freetext?: string }) => Promise<void>;
  onClose: () => void;
}) {
  const [mode, setMode] = useState<"struct" | "free">("struct");
  const [name, setName] = useState("");
  const [layers, setLayers] = useState("");
  const [freetext, setFreetext] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true);
    try {
      if (mode === "struct") {
        await onSubmit({
          name: name.trim(),
          layers: layers.split(",").map((s) => s.trim()).filter(Boolean),
        });
      } else {
        await onSubmit({ freetext: freetext.trim() });
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: -6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -6 }}
      className="card p-4 space-y-3"
    >
      <div className="flex gap-2">
        <button
          className={"btn " + (mode === "struct" ? "btn-primary" : "")}
          onClick={() => setMode("struct")}
        >
          Домен и слои
        </button>
        <button
          className={"btn " + (mode === "free" ? "btn-primary" : "")}
          onClick={() => setMode("free")}
        >
          Свободной строкой
        </button>
        <button className="btn ml-auto" onClick={onClose}>Отмена</button>
      </div>
      {mode === "struct" ? (
        <>
          <input
            placeholder="Название домена"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <input
            placeholder="Слои через запятую (можно пусто — Planner сгенерирует)"
            value={layers}
            onChange={(e) => setLayers(e.target.value)}
          />
        </>
      ) : (
        <textarea
          rows={3}
          placeholder="Я хочу также исследовать…"
          value={freetext}
          onChange={(e) => setFreetext(e.target.value)}
        />
      )}
      <button
        className="btn btn-primary"
        disabled={busy || (mode === "struct" ? !name.trim() : !freetext.trim())}
        onClick={submit}
      >
        {busy ? "Запускаю…" : "Добавить домен"}
      </button>
    </motion.div>
  );
}
