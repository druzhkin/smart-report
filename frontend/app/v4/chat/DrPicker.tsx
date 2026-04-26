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
    label: "Tavily",
    price: "≈ $0.005 (basic) / $0.02 (advanced)",
    when: "Дешёвый общий веб. Хорош для новостей, сайтов компаний, быстрых проверок.",
    mode: "integrated",
    badge: "💰 самый дешёвый",
  },
  {
    key: "exa",
    label: "Exa",
    price: "≈ $0.012 / прогон",
    when: "Семантический поиск похожих статей и блогов. \"Найди мне работы про X\".",
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
  onIntegrated: (service: AutoDRService, opts?: { mode?: ValyuResearchMode }) => Promise<void> | void;
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

  const handleClick = async (svc: DrServiceMeta) => {
    if (disabled || busyKey) return;
    if (svc.mode === "integrated") {
      if (svc.key === "valyu") {
        await onIntegrated("valyu", { mode: valyuMode });
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
              {svc.key === "valyu" && (
                <div className="valyu-mode-row">
                  <div className="valyu-mode-label">Режим:</div>
                  <div className="valyu-mode-chips">
                    {VALYU_MODES.map((m) => (
                      <button
                        key={m.key}
                        type="button"
                        className={
                          "valyu-mode-chip" + (valyuMode === m.key ? " valyu-mode-chip--active" : "")
                        }
                        onClick={() => setValyuMode(m.key)}
                        disabled={disabled || !!busyKey}
                        title={`${m.label} · ${m.price} · ${m.eta}`}
                      >
                        <span className="valyu-mode-chip__name">{m.label}</span>
                        <span className="valyu-mode-chip__meta">{m.price} · {m.eta}</span>
                      </button>
                    ))}
                  </div>
                </div>
              )}
              <div className="dr-card__actions">
                <button
                  type="button"
                  className="dr-card__btn dr-card__btn--primary"
                  onClick={() => handleClick(svc)}
                  disabled={disabled || !!busyKey}
                >
                  {isBusy
                    ? "Запускаю…"
                    : svc.key === "valyu"
                    ? `Запустить Valyu Research (${VALYU_MODES.find(m => m.key === valyuMode)?.price}) →`
                    : svc.mode === "integrated"
                    ? "Запустить →"
                    : "Открыть и скопировать промт →"}
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
