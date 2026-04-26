"use client";

import { useEffect, useState } from "react";

export type PipelineModel = "sonnet" | "opus";

const STORAGE_KEY = "smartReport.pipelineModel";

export function getPipelineModel(): PipelineModel {
  if (typeof window === "undefined") return "sonnet";
  const v = window.localStorage.getItem(STORAGE_KEY);
  return v === "opus" ? "opus" : "sonnet";
}

interface Props {
  className?: string;
  compact?: boolean;
  onChange?: (model: PipelineModel) => void;
}

export function ModelPicker({ className, compact, onChange }: Props) {
  const [model, setModel] = useState<PipelineModel>("sonnet");

  useEffect(() => {
    setModel(getPipelineModel());
  }, []);

  function select(next: PipelineModel) {
    setModel(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {}
    onChange?.(next);
  }

  return (
    <div className={`vd-model-picker ${className ?? ""}`} role="group" aria-label="Модель пайплайна">
      {!compact && <span className="vd-mp-label">Модель</span>}
      <button
        type="button"
        className={model === "sonnet" ? "active" : ""}
        onClick={() => select("sonnet")}
        aria-pressed={model === "sonnet"}
      >
        Sonnet
      </button>
      <button
        type="button"
        className={model === "opus" ? "active" : ""}
        onClick={() => select("opus")}
        aria-pressed={model === "opus"}
      >
        Opus
      </button>
    </div>
  );
}
