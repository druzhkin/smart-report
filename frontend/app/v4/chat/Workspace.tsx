"use client";

// Smart Report v.IV — main Workspace (App) component
// Ported from "Smart Report v.IV.html" App() function

import {
  useState,
  useEffect,
  useRef,
  useCallback,
} from "react";
import type { ChatMessage, Artifact, Phase, ToastState } from "./types";
import { MOCK, MOCK_PROJECTS } from "./mockData";
import { Msg, Thinking, ArtifactRef } from "./primitives";
import {
  PromptArtifact,
  UploadArtifact,
  CritiqueArtifact,
  ReportArtifact,
} from "./ArtifactContent";

const PHASE = {
  START: "start" as Phase,
  PROMPT: "prompt" as Phase,
  UPLOAD: "upload" as Phase,
  CRITIQUE: "critique" as Phase,
  TOPUP: "topup" as Phase,
  FINAL: "final" as Phase,
  DONE: "done" as Phase,
};

const PHASE_STEPS = [
  { key: "intake", num: "01", label: "Вопрос", when: (p: Phase) => p === "start" },
  { key: "prompt", num: "02", label: "Промт", when: (p: Phase) => p === "prompt" || p === "upload" },
  { key: "critique", num: "03", label: "Критика", when: (p: Phase) => p === "critique" },
  { key: "topup", num: "04", label: "Добор", when: (p: Phase) => p === "topup" },
  { key: "final", num: "05", label: "Отчёт", when: (p: Phase) => p === "done" },
];

const INITIAL_MESSAGE: ChatMessage = {
  id: "m0",
  role: "system",
  kind: "text",
  content:
    "Я — Smart Report. Помогу с глубоким исследованием по одному вопросу.\n\nСформулируйте задачу так, как если бы вы ставили её старшему аналитику. Я превращу её в research-промт, соберу результаты внешних DR, найду противоречия и соберу отчёт уровня акционера.",
};

export default function Workspace() {
  const mock = MOCK;

  // ===== State =====
  const [messages, setMessages] = useState<ChatMessage[]>(() => {
    if (typeof window === "undefined") return [INITIAL_MESSAGE];
    const saved = localStorage.getItem("sr-msgs-v2");
    if (saved) {
      try {
        return JSON.parse(saved) as ChatMessage[];
      } catch (_) {}
    }
    return [INITIAL_MESSAGE];
  });

  const [phase, setPhase] = useState<Phase>(() => {
    if (typeof window === "undefined") return PHASE.START;
    return (localStorage.getItem("sr-phase-v2") as Phase) || PHASE.START;
  });

  const [cost, setCost] = useState<number>(() => {
    if (typeof window === "undefined") return 0;
    return +(localStorage.getItem("sr-cost-v2") || 0);
  });

  const [sessionTitle, setSessionTitle] = useState(() => {
    if (typeof window === "undefined") return "Новая сессия";
    return localStorage.getItem("sr-title-v2") || "Новая сессия";
  });

  const [input, setInput] = useState("");
  const [activeCite, setActiveCite] = useState<number | null>(null);
  const [pending, setPending] = useState(false);
  const [artifact, setArtifact] = useState<Artifact | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);

  const [expandedProjects, setExpandedProjects] = useState<
    Record<string, boolean>
  >(() => {
    if (typeof window === "undefined") return { "p-premium-resi": true };
    const saved = localStorage.getItem("sr-expanded-v2");
    if (saved) {
      try {
        return JSON.parse(saved);
      } catch (_) {}
    }
    return { "p-premium-resi": true };
  });

  const [activeProjectId, setActiveProjectId] = useState("p-premium-resi");
  const [sidebarQuery, setSidebarQuery] = useState("");
  const [costOpen, setCostOpen] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);
  const [toast, setToast] = useState<ToastState | null>(null);
  const [exportOpen, setExportOpen] = useState(false);

  const [theme, setTheme] = useState<"light" | "dark">(() => {
    if (typeof window === "undefined") return "light";
    const saved = localStorage.getItem("sr-theme");
    if (saved === "dark" || saved === "light") return saved;
    return window.matchMedia?.("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  });

  // ===== Refs =====
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  // ===== Effects =====
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("sr-theme", theme);
  }, [theme]);

  useEffect(() => {
    localStorage.setItem("sr-expanded-v2", JSON.stringify(expandedProjects));
  }, [expandedProjects]);

  useEffect(() => {
    // Save state, but filter out thinking messages (they have onDone callbacks
    // which aren't serializable — we store them as text kind for restoration)
    const toSave = messages.filter((m) => m.kind !== "thinking");
    localStorage.setItem("sr-msgs-v2", JSON.stringify(toSave));
    localStorage.setItem("sr-phase-v2", phase);
    localStorage.setItem("sr-cost-v2", String(cost));
    localStorage.setItem("sr-title-v2", sessionTitle);
  }, [messages, phase, cost, sessionTitle]);

  // Autoscroll
  useEffect(() => {
    if (!scrollRef.current) return;
    const el = scrollRef.current;
    requestAnimationFrame(() => {
      el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    });
  }, [messages.length, pending]);

  // Textarea autosize
  useEffect(() => {
    const t = textareaRef.current;
    if (!t) return;
    t.style.height = "auto";
    t.style.height = Math.min(180, Math.max(44, t.scrollHeight)) + "px";
  }, [input]);

  // Keyboard shortcuts
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      if (!mod) return;
      const k = e.key.toLowerCase();
      if (k === "k") {
        e.preventDefault();
        setSidebarOpen(true);
        setTimeout(() => searchRef.current?.focus(), 60);
      } else if (k === "n") {
        e.preventDefault();
        setConfirmReset(true);
      } else if (k === "/") {
        e.preventDefault();
        textareaRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Esc to close source panel
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && activeCite !== null) {
        setActiveCite(null);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [activeCite]);

  // ===== Helpers =====
  const push = useCallback(
    (msg: Omit<ChatMessage, "id">) =>
      setMessages((ms) => [
        ...ms,
        { id: "m" + (ms.length + 1) + "-" + Date.now(), ...msg },
      ]),
    []
  );

  const openSource = useCallback((n: number) => setActiveCite(n), []);
  const closeSource = () => setActiveCite(null);

  const showToast = (
    text: string,
    action?: { label: string; run: () => void },
    duration = 4500
  ) => {
    setToast({ text, action });
    setTimeout(() => setToast(null), duration);
  };

  const toggleProject = (id: string) =>
    setExpandedProjects((p) => ({ ...p, [id]: !p[id] }));

  // ===== Copy prompt =====
  const copyPrompt = useCallback(() => {
    const flat = mock.promptSections
      .map((s) => {
        const body =
          s.body ||
          (s.bullets ? s.bullets.map((b) => "— " + b).join("\n") : "");
        return `## ${s.title}\n\n${body}`;
      })
      .join("\n\n");
    try {
      navigator.clipboard.writeText(flat);
    } catch (_) {}
    showToast("Промт скопирован — 1 482 слова");
  }, [mock.promptSections]);

  // ===== Flow handlers =====
  const onSubmitQuestion = useCallback(
    (text: string) => {
      if (!text.trim() || pending) return;
      if (sessionTitle === "Новая сессия") {
        const words = text.split(" ").slice(0, 7).join(" ");
        setSessionTitle(words + (text.split(" ").length > 7 ? "…" : ""));
      }
      push({ role: "user", kind: "text", content: text });
      setInput("");
      setPending(true);

      push({
        role: "system",
        kind: "thinking",
        traces: [
          "разбираю вопрос на подвопросы",
          "выделено 8 подвопросов · сегмент: business + premium",
          "подбор источников · 12 приоритетных",
          "генерация промта · структура 6 разделов",
          "финализация директив · добавлен критерий A/B/C",
          "выбор инструмента · рекомендован Claude Research",
        ],
        onDone: () => {
          setMessages((ms) => ms.filter((m) => m.kind !== "thinking"));
          setCost((c) => c + 12.4);
          push({
            role: "system",
            kind: "text",
            content:
              "Промт готов — 1 482 слова, 6 разделов, явная директива «Сводная таблица данных» в конце.\n\nРекомендую Claude Research: задача требует синтеза 50+ источников и корректной маркировки неподтверждённых цифр.",
          });
          push({
            role: "system",
            kind: "ref",
            refKind: "prompt",
            title: "Research-промт",
            subtitle: "1 482 слова · 6 разделов · Claude Research",
            accent: true,
          });
          push({
            role: "system",
            kind: "cta",
            primary: "Копировать и запустить внешний DR →",
            action: "copy-prompt",
            secondary: "Пропустить — я уже запустил",
            secondaryAction: "go-upload-stage",
          });
          setPhase(PHASE.PROMPT);
          setArtifact({ kind: "prompt" });
          setPending(false);
        },
      });
    },
    [pending, sessionTitle, push]
  );

  const goToUploadStage = useCallback(() => {
    push({ role: "user", kind: "text", content: "Я уже запустил внешний DR" });
    push({
      role: "system",
      kind: "text",
      content:
        "Хорошо. Когда отчёты будут готовы — загружайте их. Поддерживаю .md, .txt, .pdf — до 10 файлов за раз.",
    });
    push({
      role: "system",
      kind: "ref",
      refKind: "upload",
      title: "Загрузка отчётов",
      subtitle: "ожидание файлов",
    });
    push({
      role: "system",
      kind: "cta",
      primary: "Симулировать загрузку (demo)",
      action: "go-upload",
    });
    setArtifact({ kind: "upload-stage" });
    setPhase(PHASE.UPLOAD);
  }, [push]);

  const actUpload = useCallback(() => {
    push({ role: "user", kind: "text", content: "Отчёты готовы — вот они" });
    setPending(true);
    push({
      role: "system",
      kind: "thinking",
      traces: [
        "читаю Claude-Research-moscow-premium-v1.md · 14 820 слов",
        "читаю Perplexity-DR-amenities-benchmark.md · 5 412 слов",
        "читаю OpenAI-DR-developer-economics.md · 7 104 слов",
        "читаю Intermark-Q1-2026-notes.md · 2 108 слов",
        "читаю NF-Group-premium-residential-2025.md · 3 240 слов",
        "извлечение фактов · 312 утверждений · 94 цифры",
        "сверка между источниками · поиск противоречий",
      ],
      onDone: () => {
        setMessages((ms) => ms.filter((m) => m.kind !== "thinking"));
        setCost((c) => c + 176.72);
        push({
          role: "system",
          kind: "ref",
          refKind: "upload",
          title: "5 отчётов загружено",
          subtitle: "32 684 слов · 94 метрики",
        });
        push({
          role: "system",
          kind: "text",
          content:
            "Прочитал 5 отчётов — 32 684 слов, 94 числовых утверждения. Нашёл 7 согласий, 5 противоречий, 5 пробелов и 3 неподтверждённые цифры.\n\nПротиворечия — главное. Разбираем?",
        });
        push({
          role: "system",
          kind: "ref",
          refKind: "critique",
          title: "Критика и сверка",
          subtitle: "7 · 5 · 5 · 3",
          accent: true,
        });
        push({
          role: "system",
          kind: "cta",
          primary: "Запустить followup-добор",
          action: "go-topup",
          secondary: "Пропустить — собирать финал",
          secondaryAction: "go-final-direct",
        });
        setPhase(PHASE.CRITIQUE);
        setArtifact({ kind: "critique" });
        setPending(false);
      },
    });
  }, [push]);

  const actTopup = useCallback(() => {
    push({
      role: "user",
      kind: "text",
      content: "Запускай followup — хочу закрыть пробелы",
    });
    setPending(true);
    push({
      role: "system",
      kind: "thinking",
      traces: [
        "генерация followup-промта · 420 слов",
        "ожидание загрузки followup-отчёта",
        "приём Claude-Research-followup.md · 4 640 слов",
        "сверка: закрылось 4 из 5 пробелов",
        "IT vs традиционный бизнес — остался качественным",
      ],
      onDone: () => {
        setMessages((ms) => ms.filter((m) => m.kind !== "thinking"));
        setCost((c) => c + 64.08);
        push({
          role: "system",
          kind: "text",
          content:
            "Добор сработал. Закрылись: ROI сигарных, фасадные материалы, МОПы, международная 10-летняя траектория. Не закрылся поведенческий разрез IT vs традиционный бизнес — обозначу явно как ограничение.\n\nБаза достаточна для отчёта уровня акционера.",
        });
        push({
          role: "system",
          kind: "cta",
          primary: "Собрать финальный отчёт →",
          action: "go-final",
        });
        setPhase(PHASE.TOPUP);
        setPending(false);
      },
    });
  }, [push]);

  const actFinal = useCallback(() => {
    setPending(true);
    push({
      role: "system",
      kind: "thinking",
      traces: [
        "сборка документа · 6 разделов",
        "QA секция · 8 прямых ответов",
        "извлечение headline-цифр · 7 значений",
        "ранжирование факторов · 11 позиций",
        "верстка таблиц · 3 штуки",
        "библиография · 74 источника",
        "финальная проверка цитирования",
      ],
      onDone: () => {
        setMessages((ms) => ms.filter((m) => m.kind !== "thinking"));
        setCost((c) => Math.max(c + 594, 847.2));
        push({
          role: "system",
          kind: "text",
          content:
            "Отчёт готов. Открыл справа — там sticky-оглавление слева, цифры с [N] кликабельны. Для экспорта — кнопки в шапке артефакта.",
        });
        push({
          role: "system",
          kind: "ref",
          refKind: "report",
          title: mock.finalReport.title,
          subtitle: "74 источника · ₽ 847",
          accent: true,
        });
        setPhase(PHASE.DONE);
        setArtifact({ kind: "report" });
        setPending(false);
      },
    });
  }, [push, mock.finalReport.title]);

  const actFinalDirect = useCallback(() => {
    push({
      role: "user",
      kind: "text",
      content: "Пропустим добор — базы достаточно",
    });
    actFinal();
  }, [push, actFinal]);

  const onCta = useCallback(
    (action: string) => {
      if (pending) return;
      if (action === "copy-prompt") {
        copyPrompt();
        goToUploadStage();
      } else if (action === "go-upload-stage") {
        goToUploadStage();
      } else if (action === "go-upload") {
        actUpload();
      } else if (action === "go-topup") {
        actTopup();
      } else if (action === "go-final") {
        actFinal();
      } else if (action === "go-final-direct") {
        actFinalDirect();
      }
    },
    [
      pending,
      copyPrompt,
      goToUploadStage,
      actUpload,
      actTopup,
      actFinal,
      actFinalDirect,
    ]
  );

  const onSend = useCallback(() => {
    if (!input.trim() || pending) return;
    if (phase === PHASE.START) {
      onSubmitQuestion(input);
    } else {
      push({ role: "user", kind: "text", content: input });
      setInput("");
      push({
        role: "system",
        kind: "text",
        content:
          "В этом демо после финального отчёта диалог не продолжается. В продакшене система ответит на уточняющие вопросы из уже собранной базы источников.",
      });
    }
  }, [input, pending, phase, onSubmitQuestion, push]);

  const onKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSend();
    }
  };

  const doReset = () => {
    const backup = { messages, phase, cost, sessionTitle };
    localStorage.removeItem("sr-msgs-v2");
    localStorage.removeItem("sr-phase-v2");
    localStorage.removeItem("sr-cost-v2");
    localStorage.removeItem("sr-title-v2");
    setMessages([INITIAL_MESSAGE]);
    setPhase(PHASE.START);
    setCost(0);
    setSessionTitle("Новая сессия");
    setArtifact(null);
    setConfirmReset(false);
    showToast(
      "Сессия очищена",
      {
        label: "отменить",
        run: () => {
          setMessages(backup.messages);
          setPhase(backup.phase);
          setCost(backup.cost);
          setSessionTitle(backup.sessionTitle);
        },
      },
      8000
    );
  };

  // ===== Render message =====
  const renderMsg = (m: ChatMessage) => {
    if (m.kind === "text") {
      return (
        <Msg key={m.id} role={m.role}>
          {m.content?.split("\n\n").map((p, j) => <p key={j}>{p}</p>)}
        </Msg>
      );
    }
    if (m.kind === "thinking") {
      return (
        <Msg key={m.id} role="system">
          <Thinking
            traces={m.traces || []}
            duration={2200}
            onDone={m.onDone}
          />
        </Msg>
      );
    }
    if (m.kind === "ref") {
      const isActive =
        artifact?.kind === m.refKind ||
        (artifact?.kind === "upload-stage" && m.refKind === "upload");
      return (
        <Msg key={m.id} role="system">
          <ArtifactRef
            kind={m.refKind || ""}
            title={m.title || ""}
            subtitle={m.subtitle || ""}
            active={isActive}
            accent={m.accent}
            onClick={() =>
              setArtifact({ kind: m.refKind as Artifact["kind"] })
            }
          />
        </Msg>
      );
    }
    if (m.kind === "cta") {
      return (
        <Msg key={m.id} role="system">
          <div className="inline-actions">
            <button
              className="inline-btn primary"
              onClick={() => onCta(m.action || "")}
            >
              {m.primary}
            </button>
            {m.secondary && (
              <button
                className="inline-btn"
                onClick={() => onCta(m.secondaryAction || m.action || "")}
              >
                {m.secondary}
              </button>
            )}
          </div>
        </Msg>
      );
    }
    return null;
  };

  // ===== Phase stepper =====
  const currentStepIdx = PHASE_STEPS.findIndex((s) => s.when(phase));

  // ===== Artifact header =====
  const artifactHead = (() => {
    if (!artifact) return null;
    if (artifact.kind === "prompt") {
      return {
        kind: "Промт",
        title: "Research-промт для Claude Research",
        actions: (
          <>
            <button
              className="icon-btn"
              onClick={() =>
                showToast("Редактирование промта — в следующей итерации")
              }
            >
              изменить
            </button>
            <button className="icon-btn primary" onClick={copyPrompt}>
              скопировать
            </button>
          </>
        ),
      };
    }
    if (artifact.kind === "upload" || artifact.kind === "upload-stage") {
      return {
        kind: "Загрузка",
        title:
          artifact.kind === "upload"
            ? "Принятые отчёты (5)"
            : "Ожидание файлов",
        actions: (
          <button
            className="icon-btn primary"
            onClick={() =>
              artifact.kind === "upload-stage" ? actUpload() : null
            }
          >
            {artifact.kind === "upload-stage"
              ? "имитировать загрузку"
              : "добавить ещё"}
          </button>
        ),
      };
    }
    if (artifact.kind === "critique") {
      return {
        kind: "Критика",
        title: "Сверка пяти отчётов",
        actions: (
          <button
            className="icon-btn primary"
            onClick={() => {
              setArtifact(null);
              actTopup();
            }}
          >
            запустить добор
          </button>
        ),
      };
    }
    if (artifact.kind === "report") {
      return {
        kind: "Отчёт",
        title: mock.finalReport.title,
        actions: (
          <>
            <button className="icon-btn" onClick={() => setExportOpen(true)}>
              <svg
                width="11"
                height="11"
                viewBox="0 0 12 12"
                fill="none"
                style={{ marginRight: 5, verticalAlign: "-1px" }}
              >
                <path
                  d="M6 1.5v6.2M3.3 5.5L6 8.2l2.7-2.7M2 10.2h8"
                  stroke="currentColor"
                  strokeWidth="1.3"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
              экспорт
            </button>
            <button
              className="icon-btn accent"
              onClick={() => showToast("Отчёт расшарен по ссылке (demo)")}
            >
              поделиться →
            </button>
          </>
        ),
      };
    }
    return null;
  })();

  // ===== Source panel data =====
  const src = mock.finalReport.bibliography.find((b) => b.n === activeCite);

  // ===== Render =====
  return (
    <div className="ws-root">
      {/* ========== TOP BAR ========== */}
      <header className="topbar">
        <div className="brand">
          <button
            className="topbar-icon-btn"
            onClick={() => setSidebarOpen((s) => !s)}
            title="Сессии"
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path
                d="M2 4h12M2 8h12M2 12h12"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="square"
              />
            </svg>
          </button>
          <div className="brand-mark">SR</div>
          <div className="brand-name">Smart Report</div>
        </div>

        <div className="topbar-center">
          <input
            className="session-title"
            value={sessionTitle === "Новая сессия" ? "" : sessionTitle}
            placeholder="Назовите сессию…"
            onChange={(e) =>
              setSessionTitle(e.target.value || "Новая сессия")
            }
            title="Название сессии — кликните, чтобы изменить"
          />
        </div>

        <div className="topbar-right">
          <button
            className="topbar-icon-btn"
            onClick={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
            title={
              theme === "dark" ? "Светлая тема" : "Тёмная тема"
            }
            aria-label="Переключить тему"
          >
            {theme === "dark" ? (
              <svg
                width="15"
                height="15"
                viewBox="0 0 16 16"
                fill="none"
                aria-hidden="true"
              >
                <circle cx="8" cy="8" r="3.2" stroke="currentColor" strokeWidth="1.3" />
                <path
                  d="M8 1.5v1.8M8 12.7v1.8M1.5 8h1.8M12.7 8h1.8M3.4 3.4l1.3 1.3M11.3 11.3l1.3 1.3M12.6 3.4l-1.3 1.3M4.7 11.3l-1.3 1.3"
                  stroke="currentColor"
                  strokeWidth="1.3"
                  strokeLinecap="round"
                />
              </svg>
            ) : (
              <svg
                width="15"
                height="15"
                viewBox="0 0 16 16"
                fill="none"
                aria-hidden="true"
              >
                <path
                  d="M13.5 9.8A5.8 5.8 0 0 1 6.2 2.5a.4.4 0 0 0-.55-.4 6.5 6.5 0 1 0 8.25 8.25.4.4 0 0 0-.4-.55z"
                  stroke="currentColor"
                  strokeWidth="1.2"
                  strokeLinejoin="round"
                />
              </svg>
            )}
          </button>
          <button className="cost-btn" onClick={() => setCostOpen(true)}>
            <span>стоимость</span>
            <span className="num">
              ₽ {cost.toFixed(2).replace(".", ",")}
            </span>
          </button>
        </div>
      </header>

      {/* ========== MAIN LAYOUT ========== */}
      <div
        className={
          "app" +
          (sidebarOpen ? "" : " no-sidebar") +
          (artifact ? " artifact-open" : "")
        }
      >
        {/* ========== SIDEBAR ========== */}
        <aside className="sidebar">
          <div className="sb-top">
            <button
              className="new-session-btn"
              onClick={() => setConfirmReset(true)}
            >
              <span className="plus">+</span>
              <span>Новая сессия</span>
              <span className="kbd">⌘N</span>
            </button>
            <div className="sb-search">
              <svg
                width="12"
                height="12"
                viewBox="0 0 12 12"
                fill="none"
                className="sb-search-icon"
              >
                <circle
                  cx="5"
                  cy="5"
                  r="3.3"
                  stroke="currentColor"
                  strokeWidth="1.3"
                />
                <path
                  d="M7.5 7.5L10 10"
                  stroke="currentColor"
                  strokeWidth="1.3"
                  strokeLinecap="round"
                />
              </svg>
              <input
                ref={searchRef}
                type="text"
                placeholder="Поиск по сессиям и проектам"
                value={sidebarQuery}
                onChange={(e) => setSidebarQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Escape") {
                    setSidebarQuery("");
                    e.currentTarget.blur();
                  }
                }}
              />
              {sidebarQuery ? (
                <button
                  className="sb-search-clear"
                  onClick={() => setSidebarQuery("")}
                >
                  ✕
                </button>
              ) : (
                <span className="sb-search-kbd">⌘K</span>
              )}
            </div>
          </div>

          <div className="sb-scroll">
            {(() => {
              const q = sidebarQuery.trim().toLowerCase();
              const projectsFiltered = MOCK_PROJECTS.map((p) => ({
                ...p,
                sessions: p.sessions.filter(
                  (s) =>
                    !q ||
                    s.title.toLowerCase().includes(q) ||
                    p.name.toLowerCase().includes(q) ||
                    (p.client || "").toLowerCase().includes(q)
                ),
              })).filter(
                (p) =>
                  !q ||
                  p.sessions.length > 0 ||
                  p.name.toLowerCase().includes(q)
              );

              if (projectsFiltered.length === 0) {
                return <div className="sb-empty">Ничего не найдено</div>;
              }

              return projectsFiltered.map((proj) => {
                const expanded = q ? true : !!expandedProjects[proj.id];
                const isActive = activeProjectId === proj.id;
                const totalCost = proj.sessions.reduce(
                  (a, s) => a + Number(s.cost || 0),
                  0
                );

                return (
                  <div
                    key={proj.id}
                    className={"sb-project" + (isActive ? " active" : "")}
                  >
                    <button
                      className="sb-project-head"
                      onClick={() => {
                        toggleProject(proj.id);
                        setActiveProjectId(proj.id);
                      }}
                    >
                      <span
                        className={
                          "sb-project-chev" + (expanded ? " open" : "")
                        }
                      >
                        <svg
                          width="10"
                          height="10"
                          viewBox="0 0 10 10"
                          fill="none"
                        >
                          <path
                            d="M3.5 2L6.5 5L3.5 8"
                            stroke="currentColor"
                            strokeWidth="1.3"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          />
                        </svg>
                      </span>
                      <span
                        className={
                          "sb-project-swatch swatch-" + proj.color
                        }
                      ></span>
                      <span className="sb-project-name">{proj.name}</span>
                      <span className="sb-project-count">
                        {proj.sessions.length}
                      </span>
                    </button>
                    {expanded && (
                      <>
                        <div className="sb-project-meta">
                          <span>
                            {proj.client && proj.client !== "—"
                              ? proj.client
                              : "без клиента"}
                          </span>
                          <span>₽ {totalCost.toLocaleString("ru-RU")}</span>
                        </div>
                        <div className="sb-sessions">
                          {proj.sessions.map((s) => {
                            const showTitle = s.current
                              ? sessionTitle
                              : s.title;
                            const showCost = s.current
                              ? Math.round(cost)
                              : s.cost;
                            return (
                              <button
                                key={s.id}
                                className={
                                  "sb-session" +
                                  (s.current ? " current" : "")
                                }
                                onClick={() => {
                                  if (!s.current)
                                    showToast(
                                      "Открытие прошлых сессий — в следующей итерации"
                                    );
                                }}
                                title={showTitle}
                              >
                                <span
                                  className={
                                    "sb-session-dot " +
                                    (s.current ? "active" : "done")
                                  }
                                ></span>
                                <span className="sb-session-title">
                                  {showTitle}
                                </span>
                                <span className="sb-session-cost">
                                  ₽ {showCost}
                                </span>
                              </button>
                            );
                          })}
                        </div>
                      </>
                    )}
                  </div>
                );
              });
            })()}
          </div>

          <div className="sb-foot">
            <button
              className="sb-foot-btn"
              onClick={() =>
                showToast(
                  "Создание папки проекта — в следующей итерации"
                )
              }
            >
              <span>+</span> Новый проект
            </button>
          </div>
        </aside>

        {/* ========== CHAT COLUMN ========== */}
        <main className="chat-col">
          <div className="phase-stepper">
            {PHASE_STEPS.map((s, i) => {
              const isActive = i === currentStepIdx;
              const isDone = i < currentStepIdx;
              return (
                <div
                  key={s.key}
                  className={
                    "phase-step" +
                    (isActive ? " active" : "") +
                    (isDone ? " done" : "")
                  }
                >
                  <span className="num">{s.num}</span>
                  <span>{s.label}</span>
                </div>
              );
            })}
          </div>

          <div className="chat-scroll" ref={scrollRef}>
            <div className="chat-inner">{messages.map(renderMsg)}</div>
          </div>

          <div className="composer-wrap">
            <div className="composer">
              <textarea
                ref={textareaRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={onKey}
                placeholder={
                  phase === PHASE.START
                    ? "Опишите исследовательский вопрос…"
                    : "Напишите сообщение…"
                }
                disabled={pending}
                rows={1}
              />
              <div className="composer-actions">
                <button
                  className="composer-send"
                  onClick={onSend}
                  disabled={!input.trim() || pending}
                >
                  Отправить
                </button>
              </div>
            </div>
            <div className="composer-hint">
              <span>
                Enter · отправить&nbsp;&nbsp;&nbsp;Shift+Enter · новая
                строка&nbsp;&nbsp;&nbsp;⌘K · поиск
              </span>
              <span>Smart Report v.IV</span>
            </div>
          </div>
        </main>

        {/* ========== ARTIFACT COLUMN ========== */}
        {artifact && artifactHead && (
          <section className="artifact-col">
            <div className="artifact-head">
              <div className="artifact-head-left">
                <span className="artifact-kind">{artifactHead.kind}</span>
                <span className="artifact-title">{artifactHead.title}</span>
              </div>
              <div className="artifact-actions">
                {artifactHead.actions}
                <button
                  className="icon-btn ghost"
                  onClick={() => setArtifact(null)}
                  title="Закрыть панель"
                >
                  ✕
                </button>
              </div>
            </div>
            <div className="artifact-body">
              {artifact.kind === "prompt" && (
                <PromptArtifact mock={mock} openSource={openSource} />
              )}
              {artifact.kind === "upload" && (
                <UploadArtifact
                  files={mock.uploadedReports}
                  totalWords={mock.uploadedReports.reduce(
                    (a, b) => a + b.words,
                    0
                  )}
                />
              )}
              {artifact.kind === "upload-stage" && (
                <div className="upload-doc">
                  <h1
                    style={{
                      fontSize: 22,
                      fontWeight: 700,
                      letterSpacing: "-0.015em",
                      margin: "0 0 6px 0",
                    }}
                  >
                    Ожидание файлов
                  </h1>
                  <div
                    style={{
                      fontFamily: "var(--mono)",
                      fontSize: 11,
                      color: "var(--ink-3)",
                      letterSpacing: "0.04em",
                      marginBottom: 16,
                    }}
                  >
                    Запустите внешний DR по скопированному промту и возвращайтесь
                    сюда
                  </div>
                  <div className="upload-dropzone">
                    <div className="big">
                      Перетащите отчёты или нажмите, чтобы выбрать
                    </div>
                    <div className="small">
                      .md, .txt, .pdf · до 2 МБ каждый · до 10 файлов
                    </div>
                  </div>
                  <div
                    style={{
                      padding: 16,
                      background: "var(--paper-2)",
                      border: "1px solid var(--rule)",
                      fontSize: 12,
                      color: "var(--ink-2)",
                      lineHeight: 1.55,
                      marginTop: 8,
                    }}
                  >
                    <strong>Совет.</strong> Claude Research обычно выгружается
                    как один .md. Perplexity и OpenAI DR — как .md или копия
                    текста. Можно подкладывать и дополнительные заметки
                    (Intermark Q1-2026, NF Group) — всё учтётся в сверке.
                  </div>
                </div>
              )}
              {artifact.kind === "critique" && (
                <CritiqueArtifact
                  critique={mock.critique}
                  openSource={openSource}
                />
              )}
              {artifact.kind === "report" && (
                <ReportArtifact
                  report={mock.finalReport}
                  openSource={openSource}
                />
              )}
            </div>
          </section>
        )}
      </div>

      {/* ========== SOURCE SIDEPANEL ========== */}
      <aside className={"sidepanel" + (activeCite !== null ? " is-open" : "")}>
        <div className="sidepanel-head">
          <span className="label">
            {activeCite !== null ? `Источник [${activeCite}]` : "Источник"}
          </span>
          <button className="sidepanel-close" onClick={closeSource}>
            ✕
          </button>
        </div>
        <div className="sidepanel-body">
          {src ? (
            <>
              <div className="sidepanel-meta">
                {src.type} · {src.date}
              </div>
              <h4>{src.title}</h4>
              <div className="sidepanel-quote">
                Цитата, на которую ссылается отчёт, сверена через сводную
                таблицу данных. Уровень доверия установлен по двум независимым
                источникам.
              </div>
              <dl className="kv-list">
                <dt>ID</dt>
                <dd style={{ fontFamily: "var(--mono)" }}>
                  SRC-{String(src.n).padStart(3, "0")}
                </dd>
                <dt>Формат</dt>
                <dd>{src.type}</dd>
                <dt>Дата</dt>
                <dd>{src.date}</dd>
                <dt>Уровень</dt>
                <dd>
                  <span className="confidence a">A</span>
                </dd>
              </dl>
            </>
          ) : (
            <div style={{ color: "var(--ink-3)", fontSize: 13 }}>
              Выберите цитату в тексте отчёта.
            </div>
          )}
        </div>
      </aside>

      {/* ========== COST POPOVER ========== */}
      {costOpen && (
        <>
          <div
            className="popover-backdrop"
            onClick={() => setCostOpen(false)}
          ></div>
          <div className="popover" style={{ right: 16, top: 56 }}>
            <h4>Структура стоимости</h4>
            <div className="popover-row">
              <span>Разбор вопроса (Haiku)</span>
              <span className="v">₽ 2,40</span>
            </div>
            <div className="popover-row">
              <span>Генерация промта (Sonnet)</span>
              <span className="v">₽ 10,00</span>
            </div>
            <div className="popover-row">
              <span>Чтение 5 отчётов (Opus × 6)</span>
              <span className="v">₽ 176,72</span>
            </div>
            <div className="popover-row">
              <span>Сверка и критика (Opus × 3)</span>
              <span className="v">₽ 64,08</span>
            </div>
            <div className="popover-row">
              <span>Добор (Opus × 2)</span>
              <span className="v">₽ 64,08</span>
            </div>
            <div className="popover-row">
              <span>Сборка отчёта (Opus × 3)</span>
              <span className="v">₽ 529,92</span>
            </div>
            <div className="popover-row total">
              <span>Итого (14 вызовов Opus, 47 мин)</span>
              <span className="v">
                ₽ {cost.toFixed(2).replace(".", ",")}
              </span>
            </div>
          </div>
        </>
      )}

      {/* ========== RESET CONFIRM ========== */}
      {confirmReset && (
        <div
          className="modal-backdrop"
          onClick={() => setConfirmReset(false)}
        >
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>Начать новую сессию?</h3>
            <p>
              Текущий чат и собранный отчёт будут закрыты. Восстановить можно
              будет сразу после — через кнопку «отменить» в уведомлении.
            </p>
            <div className="modal-actions">
              <button
                className="inline-btn"
                onClick={() => setConfirmReset(false)}
              >
                Отмена
              </button>
              <button className="inline-btn primary" onClick={doReset}>
                Начать новую
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ========== EXPORT MENU ========== */}
      {exportOpen && (
        <>
          <div
            className="popover-backdrop"
            onClick={() => setExportOpen(false)}
          ></div>
          <div className="export-menu" role="menu">
            <div className="export-group">
              <div className="export-group-label">Быстрый вывод</div>
              <button
                className="export-item"
                onClick={() => {
                  setExportOpen(false);
                  showToast(
                    "One-pager — ключевая цифра + 8 тезисов, 1 стр. Word"
                  );
                }}
              >
                <span className="export-icon one-pager">
                  <svg
                    width="18"
                    height="18"
                    viewBox="0 0 18 18"
                    fill="none"
                    aria-hidden="true"
                  >
                    <rect
                      x="2"
                      y="3"
                      width="14"
                      height="12"
                      rx="1.5"
                      stroke="currentColor"
                      strokeWidth="1.3"
                    />
                    <rect
                      x="4"
                      y="5.5"
                      width="5"
                      height="3"
                      fill="currentColor"
                      opacity="0.35"
                    />
                    <rect x="10" y="5.5" width="4" height="1.2" fill="currentColor" />
                    <rect x="10" y="7.3" width="4" height="1.2" fill="currentColor" />
                    <rect
                      x="4"
                      y="10"
                      width="10"
                      height="1"
                      fill="currentColor"
                      opacity="0.5"
                    />
                    <rect
                      x="4"
                      y="12"
                      width="8"
                      height="1"
                      fill="currentColor"
                      opacity="0.5"
                    />
                  </svg>
                </span>
                <span className="export-text">
                  <span className="export-name">One-pager</span>
                  <span className="export-meta">Word · 1 страница</span>
                </span>
              </button>
              <button
                className="export-item"
                onClick={() => {
                  setExportOpen(false);
                  showToast(
                    "Markdown — исходник с разделами, таблицами и [N]-ссылками"
                  );
                }}
              >
                <span className="export-icon md">
                  <svg
                    width="18"
                    height="18"
                    viewBox="0 0 18 18"
                    fill="none"
                    aria-hidden="true"
                  >
                    <rect
                      x="1.5"
                      y="4"
                      width="15"
                      height="10"
                      rx="1.5"
                      stroke="currentColor"
                      strokeWidth="1.3"
                    />
                    <path
                      d="M4 11V7l1.6 2 1.6-2v4M10.5 7v4M9 9.5l1.5 1.5L12 9.5"
                      stroke="currentColor"
                      strokeWidth="1.3"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </span>
                <span className="export-text">
                  <span className="export-name">Markdown</span>
                  <span className="export-meta">.md</span>
                </span>
              </button>
            </div>

            <div className="export-group">
              <div className="export-group-label">Сгенерировать через Gamma</div>
              <button
                className="export-item"
                onClick={() => {
                  setExportOpen(false);
                  showToast(
                    "Gamma Presentation — AI-презентация из отчёта в .pptx"
                  );
                }}
              >
                <span className="export-icon gamma">
                  <svg
                    width="18"
                    height="18"
                    viewBox="0 0 18 18"
                    fill="none"
                    aria-hidden="true"
                  >
                    <path
                      d="M9 2.2l1.1 2.5 2.7.3-2 1.9.5 2.7L9 8.3 6.7 9.6l.5-2.7-2-1.9 2.7-.3L9 2.2z"
                      fill="currentColor"
                    />
                    <path
                      d="M4 13l.55 1.25L5.8 14.8l-1.25.55L4 16.6l-.55-1.25L2.2 14.8l1.25-.55L4 13z"
                      fill="currentColor"
                      opacity="0.75"
                    />
                    <path
                      d="M14 11l.4 1 1 .4-1 .4-.4 1-.4-1-1-.4 1-.4.4-1z"
                      fill="currentColor"
                      opacity="0.55"
                    />
                  </svg>
                </span>
                <span className="export-text">
                  <span className="export-name">
                    <span className="sparkle-badge">✨</span> Gamma Presentation
                  </span>
                  <span className="export-meta">AI · .pptx</span>
                </span>
              </button>
              <button
                className="export-item"
                onClick={() => {
                  setExportOpen(false);
                  showToast(
                    "Gamma Presentation — AI-презентация из отчёта в .pdf"
                  );
                }}
              >
                <span className="export-icon gamma">
                  <svg
                    width="18"
                    height="18"
                    viewBox="0 0 18 18"
                    fill="none"
                    aria-hidden="true"
                  >
                    <path
                      d="M9 2.2l1.1 2.5 2.7.3-2 1.9.5 2.7L9 8.3 6.7 9.6l.5-2.7-2-1.9 2.7-.3L9 2.2z"
                      fill="currentColor"
                    />
                    <path
                      d="M4 13l.55 1.25L5.8 14.8l-1.25.55L4 16.6l-.55-1.25L2.2 14.8l1.25-.55L4 13z"
                      fill="currentColor"
                      opacity="0.75"
                    />
                    <path
                      d="M14 11l.4 1 1 .4-1 .4-.4 1-.4-1-1-.4 1-.4.4-1z"
                      fill="currentColor"
                      opacity="0.55"
                    />
                  </svg>
                </span>
                <span className="export-text">
                  <span className="export-name">
                    <span className="sparkle-badge">✨</span> Gamma Presentation
                  </span>
                  <span className="export-meta">AI · .pdf</span>
                </span>
              </button>
            </div>

            <div className="export-group">
              <div className="export-group-label">Классика</div>
              <button
                className="export-item"
                onClick={() => {
                  setExportOpen(false);
                  showToast(".docx — editable текст, разделы, таблицы, источники");
                }}
              >
                <span className="export-icon docx">
                  <svg
                    width="18"
                    height="18"
                    viewBox="0 0 18 18"
                    fill="none"
                    aria-hidden="true"
                  >
                    <path
                      d="M3 2.5h7.5L15 7v8.5H3v-13z"
                      stroke="currentColor"
                      strokeWidth="1.3"
                      strokeLinejoin="round"
                    />
                    <path
                      d="M10.5 2.5V7H15"
                      stroke="currentColor"
                      strokeWidth="1.3"
                      strokeLinejoin="round"
                    />
                    <path
                      d="M5 9.5l1 3 1-2 1 2 1-3"
                      stroke="currentColor"
                      strokeWidth="1.2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </span>
                <span className="export-text">
                  <span className="export-name">Word Document</span>
                  <span className="export-meta">.docx</span>
                </span>
              </button>
              <button
                className="export-item"
                onClick={() => {
                  setExportOpen(false);
                  showToast(".pptx — 12 слайдов с headline-цифрами и графиками");
                }}
              >
                <span className="export-icon pptx">
                  <svg
                    width="18"
                    height="18"
                    viewBox="0 0 18 18"
                    fill="none"
                    aria-hidden="true"
                  >
                    <rect
                      x="2"
                      y="3"
                      width="14"
                      height="9.5"
                      rx="1"
                      stroke="currentColor"
                      strokeWidth="1.3"
                    />
                    <path
                      d="M9 12.5V15M6 15h6"
                      stroke="currentColor"
                      strokeWidth="1.3"
                      strokeLinecap="round"
                    />
                    <rect
                      x="4.5"
                      y="5.5"
                      width="4"
                      height="5"
                      fill="currentColor"
                      opacity="0.45"
                    />
                    <rect
                      x="10"
                      y="5.5"
                      width="3.5"
                      height="2.2"
                      fill="currentColor"
                      opacity="0.65"
                    />
                    <rect
                      x="10"
                      y="8.3"
                      width="3.5"
                      height="2.2"
                      fill="currentColor"
                      opacity="0.45"
                    />
                  </svg>
                </span>
                <span className="export-text">
                  <span className="export-name">Presentation</span>
                  <span className="export-meta">.pptx · 12 слайдов</span>
                </span>
              </button>
              <button
                className="export-item"
                onClick={() => {
                  setExportOpen(false);
                  showToast(".pdf — print-ready версия отчёта");
                }}
              >
                <span className="export-icon pdf">
                  <svg
                    width="18"
                    height="18"
                    viewBox="0 0 18 18"
                    fill="none"
                    aria-hidden="true"
                  >
                    <path
                      d="M3 2.5h7.5L15 7v8.5H3v-13z"
                      stroke="currentColor"
                      strokeWidth="1.3"
                      strokeLinejoin="round"
                    />
                    <path
                      d="M10.5 2.5V7H15"
                      stroke="currentColor"
                      strokeWidth="1.3"
                      strokeLinejoin="round"
                    />
                    <path
                      d="M5 11.5h1.4c.5 0 .9.4.9.9s-.4.9-.9.9H5v1M9 10.7v3.5h.8c.7 0 1.2-.6 1.2-1.3v-.9c0-.7-.5-1.3-1.2-1.3H9zM12 10.7v3.5M12 12.4h1.5"
                      stroke="currentColor"
                      strokeWidth="1.1"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </span>
                <span className="export-text">
                  <span className="export-name">PDF</span>
                  <span className="export-meta">.pdf · print-ready</span>
                </span>
              </button>
              <button
                className="export-item"
                onClick={() => {
                  setExportOpen(false);
                  showToast("Raw JSON — структура отчёта для интеграций");
                }}
              >
                <span className="export-icon json">
                  <svg
                    width="18"
                    height="18"
                    viewBox="0 0 18 18"
                    fill="none"
                    aria-hidden="true"
                  >
                    <path
                      d="M3 2.5h7.5L15 7v8.5H3v-13z"
                      stroke="currentColor"
                      strokeWidth="1.3"
                      strokeLinejoin="round"
                    />
                    <path
                      d="M10.5 2.5V7H15"
                      stroke="currentColor"
                      strokeWidth="1.3"
                      strokeLinejoin="round"
                    />
                    <path
                      d="M7 9.5q-1 0-1 1v1q0 .6-.7.7.7.1.7.7v1q0 1 1 1M11 9.5q1 0 1 1v1q0 .6.7.7-.7.1-.7.7v1q0 1-1 1"
                      stroke="currentColor"
                      strokeWidth="1.1"
                      strokeLinecap="round"
                    />
                  </svg>
                </span>
                <span className="export-text">
                  <span className="export-name">Raw JSON</span>
                  <span className="export-meta">.json · для интеграций</span>
                </span>
              </button>
            </div>
          </div>
        </>
      )}

      {/* ========== TOAST ========== */}
      <div className={"toast" + (toast ? " show" : "")}>
        <span>{toast?.text}</span>
        {toast?.action && (
          <button
            onClick={() => {
              toast.action?.run();
              setToast(null);
            }}
          >
            {toast.action.label}
          </button>
        )}
      </div>
    </div>
  );
}
