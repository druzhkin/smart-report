"use client";

// Smart Report v.IV — Deep Research service picker.
//
// 4 integrated (server-side via /api/v4/sessions/{id}/auto-dr):
//   valyu (with Research-mode submenu: fast / standard / heavy / max),
//   tavily, exa, perplexity
// 3 copy-launch (client-side: copy prompt → open service tab):
//   openai, claude, gemini

import { useState } from "react";
import type { AutoDRService, ValyuResearchMode } from "@/lib/apiV4";

export type ValyuModeSpec = {
  key: ValyuResearchMode;
  label: string;
  price: string;
  eta: string;
};

// Valyu Research modes — fixed prices per Valyu docs (2026-04).
export const VALYU_MODES: ValyuModeSpec[] = [
  { key: "fast",     label: "Fast",     price: "$0.10",  eta: "~5 мин" },
  { key: "standard", label: "Standard", price: "$0.50",  eta: "10-20 мин" },
  { key: "heavy",    label: "Heavy",    price: "$2.50",  eta: "~90 мин" },
  { key: "max",      label: "Max",      price: "$15.00", eta: "~3 часа" },
];

// Generic mode spec for Tavily and Exa research (different label sets).
export type ServiceModeSpec = {
  key: string;
  label: string;
  price: string;
  eta: string;
};

export const TAVILY_RESEARCH_MODES: ServiceModeSpec[] = [
  { key: "mini", label: "Mini", price: "$0.05", eta: "2-5 мин" },
  { key: "pro",  label: "Pro",  price: "$0.30", eta: "5-15 мин" },
  { key: "auto", label: "Auto", price: "≈$0.20", eta: "3-12 мин" },
];

export const EXA_RESEARCH_MODES: ServiceModeSpec[] = [
  { key: "fast",     label: "Fast",     price: "$0.10", eta: "3-7 мин" },
  { key: "standard", label: "Standard", price: "$0.50", eta: "10-20 мин" },
  { key: "pro",      label: "Pro",      price: "$2.00", eta: "30-60 мин" },
];

export type DrServiceKey =
  | AutoDRService          // valyu | tavily | exa | perplexity (integrated)
  | "openai"               // copy-launch: ChatGPT Deep Research
  | "claude"               // copy-launch: Claude Research
  | "gemini";              // copy-launch: Gemini Deep Research

export interface DrServiceMeta {
  key: DrServiceKey;
  label: string;
  price: string;
  when: string;
  mode: "integrated" | "copy-launch";
  url?: string;            // for copy-launch
  badge?: string;          // visible tag e.g. "best for filings"
}

export const DR_SERVICES: DrServiceMeta[] = [
  {
    key: "valyu",
    label: "Valyu Research",
    price: "от $0.10 до $15 (4 режима)",
    when: "Полноценный async DR: fast (5 мин), standard (10–20 мин), heavy (90 мин, fact-verification), max (3 часа, exhaustive). Лучшее качество для финансов, регуляторики, науки. Запускается в фоне, можно закрыть вкладку.",
    mode: "integrated",
    badge: "🏆 настоящий DR",
  },
  {
    key: "tavily",
    label: "Tavily Research",
    price: "от $0.05 до $0.30 (3 режима)",
    when: "Агентский DR от Tavily: mini ($0.05, 2-5 мин), pro ($0.30, 5-15 мин), auto (на усмотрение). Сильный по веб-источникам и свежим данным.",
    mode: "integrated",
    badge: "💰 быстрый и недорогой",
  },
  {
    key: "exa",
    label: "Exa Research",
    price: "от $0.10 до $2.00 (3 режима)",
    when: "Агентский DR с семантическим поиском: fast ($0.10), standard ($0.50), pro ($2.00, до 60 мин с structured output). Лучший для научных статей, блогов, similarity-исследований.",
    mode: "integrated",
  },
  {
    key: "perplexity",
    label: "Perplexity Sonar Pro",
    price: "≈ $0.50–2.00 / прогон",
    when: "LLM-исследование с цитатами. Универсальный, средняя глубина.",
    mode: "integrated",
  },
  {
    key: "openai",
    label: "ChatGPT Deep Research",
    price: "$20/мес (Plus) или $200/мес (Pro)",
    when: "Самая глубокая длинная аналитика. Открыть, вставить промт.",
    mode: "copy-launch",
    url: "https://chatgpt.com/?model=gpt-5-deep-research",
  },
  {
    key: "claude",
    label: "Claude Research",
    price: "$20/мес (Pro) или $200/мес (Max)",
    when: "Длинный контекст, аккуратные цитаты, sober выводы.",
    mode: "copy-launch",
    url: "https://claude.ai/new",
  },
  {
    key: "gemini",
    label: "Gemini Deep Research",
    price: "$20/мес (Advanced)",
    when: "Лучшая интеграция с Google и Workspace. Сильно по веб-источникам.",
    mode: "copy-launch",
    url: "https://gemini.google.com/app",
  },
];

export interface DrPickerProps {
  onIntegrated: (service: AutoDRService, opts?: { mode?: string }) => Promise<void> | void;
  onCopyLaunch: (key: DrServiceKey, url: string) => void;
  onSkip: () => void;            // "Я уже запустил — загружу .md"
  disabled?: boolean;
  busyKey?: DrServiceKey | null;
}

export function DrPicker({
  onIntegrated,
  onCopyLaunch,
  onSkip,
  disabled,
  busyKey,
}: DrPickerProps) {
  const [expanded, setExpanded] = useState<DrServiceKey | null>(null);
  const [valyuMode, setValyuMode] = useState<ValyuResearchMode>("standard");
  const [tavilyMode, setTavilyMode] = useState<string>("pro");
  const [exaMode, setExaMode] = useState<string>("standard");

  const modeFor = (key: DrServiceKey): string | undefined => {
    if (key === "valyu") return valyuMode;
    if (key === "tavily") return tavilyMode;
    if (key === "exa") return exaMode;
    return undefined;
  };

  const modesFor = (key: DrServiceKey): ServiceModeSpec[] => {
    if (key === "valyu") return VALYU_MODES;
    if (key === "tavily") return TAVILY_RESEARCH_MODES;
    if (key === "exa") return EXA_RESEARCH_MODES;
    return [];
  };

  const setModeFor = (key: DrServiceKey, value: string) => {
    if (key === "valyu") setValyuMode(value as ValyuResearchMode);
    else if (key === "tavily") setTavilyMode(value);
    else if (key === "exa") setExaMode(value);
  };

  const handleClick = async (svc: DrServiceMeta) => {
    if (disabled || busyKey) return;
    if (svc.mode === "integrated") {
      const mode = modeFor(svc.key);
      if (mode) {
        await onIntegrated(svc.key as AutoDRService, { mode });
      } else {
        await onIntegrated(svc.key as AutoDRService);
      }
    } else {
      onCopyLaunch(svc.key, svc.url || "");
    }
  };

  return (
    <div className="dr-picker">
      <div className="dr-picker__header">
        <div className="dr-picker__title">Запустить Deep Research</div>
        <div className="dr-picker__hint">
          Выберите сервис — мы запустим исследование на сервере или откроем
          сервис в новой вкладке.
        </div>
      </div>
      <div className="dr-picker__grid">
        {DR_SERVICES.map((svc) => {
          const isBusy = busyKey === svc.key;
          const isExpanded = expanded === svc.key;
          return (
            <div
              key={svc.key}
              className={`dr-card${svc.mode === "integrated" ? " dr-card--integrated" : ""}`}
            >
              <div className="dr-card__top">
                <div className="dr-card__name">
                  {svc.label}
                  {svc.badge && <span className="dr-card__badge">{svc.badge}</span>}
                </div>
                <div className="dr-card__price">{svc.price}</div>
              </div>
              <div className="dr-card__when">{svc.when}</div>
              {svc.mode === "integrated" && modesFor(svc.key).length > 0 && (() => {
                const modes = modesFor(svc.key);
                const cur = modeFor(svc.key) || "";
                return (
                  <div className="valyu-mode-row">
                    <div className="valyu-mode-label">Режим:</div>
                    <div className="valyu-mode-chips">
                      {modes.map((m) => (
                        <button
                          key={m.key}
                          type="button"
                          className={
                            "valyu-mode-chip" + (cur === m.key ? " valyu-mode-chip--active" : "")
                          }
                          onClick={() => setModeFor(svc.key, m.key)}
                          disabled={disabled || !!busyKey}
                          title={`${m.label} · ${m.price} · ${m.eta}`}
                        >
                          <span className="valyu-mode-chip__name">{m.label}</span>
                          <span className="valyu-mode-chip__meta">{m.price} · {m.eta}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                );
              })()}
              <div className="dr-card__actions">
                <button
                  type="button"
                  className="dr-card__btn dr-card__btn--primary"
                  onClick={() => handleClick(svc)}
                  disabled={disabled || !!busyKey}
                >
                  {(() => {
                    if (isBusy) return "Запускаю…";
                    if (svc.mode !== "integrated") return "Открыть и скопировать промт →";
                    const modes = modesFor(svc.key);
                    if (modes.length > 0) {
                      const cur = modes.find(m => m.key === modeFor(svc.key));
                      return `Запустить ${svc.label.replace(' Research','')} (${cur?.price ?? ""}) →`;
                    }
                    return "Запустить →";
                  })()}
                </button>
                <button
                  type="button"
                  className="dr-card__btn dr-card__btn--ghost"
                  onClick={() => setExpanded(isExpanded ? null : svc.key)}
                >
                  {isExpanded ? "свернуть" : "детали"}
                </button>
              </div>
              {isExpanded && (
                <div className="dr-card__details">
                  {svc.mode === "integrated" ? (
                    <>
                      <p>Запустится на нашем сервере. Результат появится в
                      сессии как загруженный отчёт — можно сразу анализировать.</p>
                      <p>Стоимость списывается с месячного лимита.</p>
                    </>
                  ) : (
                    <>
                      <p>Откроем сервис в новой вкладке, скопируем промт в буфер.
                      Запустите, дождитесь отчёта, скачайте .md и загрузите ниже.</p>
                      <p>Подписка оплачивается напрямую сервису, не нам.</p>
                    </>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
      <div className="dr-picker__footer">
        <button
          type="button"
          className="dr-picker__skip"
          onClick={onSkip}
          disabled={disabled || !!busyKey}
        >
          Уже запустил — загружу отчёт сам
        </button>
      </div>
    </div>
  );
}
