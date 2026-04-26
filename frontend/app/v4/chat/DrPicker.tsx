"use client";

// Smart Report v.IV — Deep Research service picker.
// Replaces the lone "Скопировать промт →" CTA with a card of 7 services.
//
// 4 integrated (server-side via /api/v4/sessions/{id}/auto-dr):
//   valyu, tavily, exa, perplexity
// 3 copy-launch (client-side: copy prompt → open service tab):
//   openai, claude, gemini

import { useState } from "react";
import type { AutoDRService } from "@/lib/apiV4";

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
    label: "Valyu",
    price: "≈ $0.01–0.02 (fast mode)",
    when: "SEC-фалинги, FRED, arXiv, PubMed. Лучший выбор для финансов, регуляторики, науки. Стандартный режим у Valyu стоит ~$0.25, но мы используем fast — быстрее и в 10× дешевле.",
    mode: "integrated",
    badge: "🏆 для отчётности",
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
  onIntegrated: (service: AutoDRService) => Promise<void> | void;
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

  const handleClick = async (svc: DrServiceMeta) => {
    if (disabled || busyKey) return;
    if (svc.mode === "integrated") {
      await onIntegrated(svc.key as AutoDRService);
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
              <div className="dr-card__actions">
                <button
                  type="button"
                  className="dr-card__btn dr-card__btn--primary"
                  onClick={() => handleClick(svc)}
                  disabled={disabled || !!busyKey}
                >
                  {isBusy
                    ? "Запускаю…"
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
