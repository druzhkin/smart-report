"use client";

// Smart Report v.IV — main Workspace (App) component
// Real backend integration: no mock data

import {
  useState,
  useEffect,
  useRef,
  useCallback,
} from "react";
import type { ChatMessage, Artifact, Phase, ToastState } from "./types";
import type { AnalysisOutput, AutoDRService, FinalReport, ResearchPrompt } from "@/lib/apiV4";
import {
  createSession,
  generatePrompt,
  uploadReports,
  analyze,
  uploadFollowup,
  synthesize,
  getSession,
  runAutoDR,
  cancelSession,
  deleteSession,
  getEvents,
  listSessions,
  getQualityGrade,
  type SessionListItem,
  type QualityGrade,
} from "@/lib/apiV4";
import { DrPicker, type DrServiceKey } from "./DrPicker";
import { ModelPicker, getPipelineModel } from "@/components/ModelPicker";
import { Msg, Thinking, ArtifactRef } from "./primitives";
import {
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

  const [sessionId, setSessionId] = useState<string | null>(() => {
    if (typeof window === "undefined") return null;
    return localStorage.getItem("sr-session-id-v2") || null;
  });

  // Stored real API data for artifact rendering
  const [promptData, setPromptData] = useState<ResearchPrompt | null>(null);
  const [analysisData, setAnalysisData] = useState<AnalysisOutput | null>(null);
  const [finalData, setFinalData] = useState<FinalReport | null>(null);

  const [input, setInput] = useState("");
  const [activeCite, setActiveCite] = useState<number | null>(null);
  const [pending, setPending] = useState(false);
  const [artifact, setArtifact] = useState<Artifact | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [sidebarQuery, setSidebarQuery] = useState("");
  const [costOpen, setCostOpen] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);
  const [toast, setToast] = useState<ToastState | null>(null);
  const [exportOpen, setExportOpen] = useState(false);
  const [drBusy, setDrBusy] = useState<DrServiceKey | null>(null);
  const [savedSessions, setSavedSessions] = useState<SessionListItem[]>([]);
  const [qualityGrade, setQualityGrade] = useState<QualityGrade | null>(null);

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
  const uploadRef = useRef<HTMLInputElement>(null);
  const followupRef = useRef<HTMLInputElement>(null);

  // ===== Effects =====
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("sr-theme", theme);
  }, [theme]);

  useEffect(() => {
    const toSave = messages.filter((m) => m.kind !== "thinking");
    localStorage.setItem("sr-msgs-v2", JSON.stringify(toSave));
    localStorage.setItem("sr-phase-v2", phase);
    localStorage.setItem("sr-cost-v2", String(cost));
    localStorage.setItem("sr-title-v2", sessionTitle);
  }, [messages, phase, cost, sessionTitle]);

  // Persist sessionId
  useEffect(() => {
    if (sessionId) {
      localStorage.setItem("sr-session-id-v2", sessionId);
    } else {
      localStorage.removeItem("sr-session-id-v2");
    }
  }, [sessionId]);

  // On mount: restore session cost/phase from backend
  useEffect(() => {
    const savedId = localStorage.getItem("sr-session-id-v2");
    if (!savedId) return;
    getSession(savedId)
      .then((s) => {
        if (s.total_cost_rub) setCost(s.total_cost_rub);
        if (s.research_prompt) setPromptData(s.research_prompt);
        if (s.analysis) setAnalysisData(s.analysis);
        if (s.final_report) setFinalData(s.final_report);
      })
      .catch(() => {
        // Session not found on backend after restart — clear local id
        localStorage.removeItem("sr-session-id-v2");
        setSessionId(null);
      });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

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

  // ===== Quality grade =====
  // Fetch only when we have a final report — pre-synth there's nothing
  // to grade. Re-fetch on sessionId change so saved-session loads pull
  // the right grade.
  useEffect(() => {
    if (!sessionId || !finalData) {
      setQualityGrade(null);
      return;
    }
    let cancelled = false;
    getQualityGrade(sessionId)
      .then((g) => { if (!cancelled) setQualityGrade(g); })
      .catch(() => { if (!cancelled) setQualityGrade(null); });
    return () => { cancelled = true; };
  }, [sessionId, finalData]);

  // ===== Saved sessions list =====
  // Refresh on mount, after cost changes (signals new server-side activity),
  // and after sessionId changes (login → reload list, new session created).
  useEffect(() => {
    let cancelled = false;
    listSessions()
      .then((rows) => {
        if (!cancelled) setSavedSessions(rows);
      })
      .catch(() => {
        // 401 → not signed in; sidebar shows empty state. No toast.
      });
    return () => { cancelled = true; };
  }, [sessionId, cost]);

  const reloadSessions = useCallback(() => {
    listSessions().then(setSavedSessions).catch(() => {});
  }, []);

  // ===== Live events polling =====
  // While a long-running call is in flight (analyze / synthesize can take
  // 5-10 minutes for Sonnet), long-poll /events so the user sees real
  // backend progress instead of staring at the static 4-trace placeholder.
  // Stops on !pending, sessionId change, or component unmount.
  useEffect(() => {
    if (!pending || !sessionId) return;
    let cancelled = false;
    let cursor = 0;
    let lastSeenSeq = -1;
    (async () => {
      while (!cancelled) {
        try {
          const r = await getEvents(sessionId, cursor, 25);
          if (cancelled) return;
          for (const ev of r.events) {
            if (ev.seq <= lastSeenSeq) continue;
            lastSeenSeq = ev.seq;
            if (ev.message && ev.message.trim()) {
              setMessages((ms) => [
                ...ms,
                {
                  id: `ev-${sessionId}-${ev.seq}`,
                  role: "system",
                  kind: "text",
                  content: `· ${ev.message}`,
                },
              ]);
            }
          }
          cursor = r.cursor;
          if (r.status === "done" || r.status === "error") return;
        } catch {
          // Long-poll error (e.g. session deleted, network blip): back off.
          await new Promise((res) => setTimeout(res, 3000));
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [pending, sessionId]);

  // ===== Saved-session load / delete =====
  const loadSavedSession = useCallback(
    async (sid: string, title?: string) => {
      if (pending) {
        showToast("Дождитесь завершения текущего шага");
        return;
      }
      try {
        const s = await getSession(sid);
        setSessionId(sid);
        setSessionTitle(title || s.raw_question.slice(0, 40) || "Сессия");
        setPromptData(s.research_prompt);
        setAnalysisData(s.analysis);
        setFinalData(s.final_report);
        setCost(s.total_cost_rub || 0);
        // Phase based on what's already done.
        let nextPhase: Phase = PHASE.START;
        if (s.final_report) nextPhase = PHASE.DONE;
        else if (s.analysis) nextPhase = PHASE.CRITIQUE;
        else if (s.source_reports?.length) nextPhase = PHASE.UPLOAD;
        else if (s.research_prompt) nextPhase = PHASE.PROMPT;
        setPhase(nextPhase);
        // Replace chat with a single welcome message — chat history wasn't
        // persisted server-side, so we render a "session restored" line + a
        // ref to the most useful artifact.
        const restored: ChatMessage = {
          id: `restored-${Date.now()}`,
          role: "system",
          kind: "text",
          content: `Сессия восстановлена. Вопрос: «${s.raw_question}». Статус: ${s.status}. ${s.final_report ? "Отчёт готов — справа." : s.analysis ? "Анализ есть — можно запустить синтез." : s.source_reports?.length ? "Загружены отчёты — можно анализировать." : s.research_prompt ? "Промт готов — выберите DR-сервис ниже." : "Начните с вопроса."}`,
        };
        setMessages([restored]);
        if (s.final_report) setArtifact({ kind: "report", data: s.final_report });
        else if (s.analysis) setArtifact({ kind: "critique", data: s.analysis });
        else if (s.research_prompt) setArtifact({ kind: "prompt", data: s.research_prompt });
        else setArtifact(null);
        showToast(`Сессия загружена: ${(title || s.raw_question).slice(0, 40)}`);
      } catch (e) {
        showToast(`Не удалось загрузить: ${e instanceof Error ? e.message : String(e)}`);
      }
    },
    [pending]
  );

  const deleteSavedSession = useCallback(
    async (sid: string) => {
      try {
        await deleteSession(sid);
        setSavedSessions((rows) => rows.filter((r) => r.session_id !== sid));
        if (sid === sessionId) {
          // The active session was deleted — clear local state.
          localStorage.removeItem("sr-session-id-v2");
          localStorage.removeItem("sr-msgs-v2");
          setSessionId(null);
          setMessages([INITIAL_MESSAGE]);
          setPhase(PHASE.START);
          setPromptData(null); setAnalysisData(null); setFinalData(null);
          setArtifact(null);
        }
        showToast("Сессия удалена");
      } catch (e) {
        showToast(`Не удалось удалить: ${e instanceof Error ? e.message : String(e)}`);
      }
    },
    [sessionId]
  );

  // ===== Cancel handler =====
  const onCancel = useCallback(async () => {
    if (!sessionId || !pending) return;
    try {
      await cancelSession(sessionId);
    } catch (e) {
      // best-effort — server-side flip might fail if session was just deleted
    }
    setMessages((ms) => [
      ...ms.filter((m) => m.kind !== "thinking"),
      {
        id: `cancel-${Date.now()}`,
        role: "system",
        kind: "text",
        content:
          "Сессия отменена. Запущенный LLM-вызов завершится в фоне (за него уже списано), но эта сессия больше не примет команд. Создайте новую через ⌘N.",
      },
    ]);
    setPending(false);
    showToast("Сессия отменена");
  }, [sessionId, pending]);

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

  // ===== Copy prompt =====
  const copyPrompt = useCallback(() => {
    if (!promptData) {
      showToast("Промт ещё не готов");
      return;
    }
    try {
      navigator.clipboard.writeText(promptData.full_prompt);
    } catch (_) {}
    showToast(`Промт скопирован — ${promptData.full_prompt.length} символов`);
  }, [promptData]);

  const copyFollowupPrompt = useCallback(() => {
    const fu = analysisData?.followup_prompt;
    if (!fu) {
      showToast("Followup-промт ещё не готов");
      return;
    }
    try {
      navigator.clipboard.writeText(fu.prompt);
    } catch (_) {}
    showToast(`Followup-промт скопирован — ${fu.prompt.length} символов`);
  }, [analysisData]);

  // ===== Real flow handlers =====
  const onSubmitQuestion = useCallback(
    async (text: string) => {
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
          "подбор структуры промта",
          "генерация research-промта",
          "финализация директив",
        ],
        onDone: () => {},
      });

      try {
        const { session_id } = await createSession(text);
        setSessionId(session_id);

        const pref = getPipelineModel();
        const prompt = await generatePrompt(session_id, pref);
        setPromptData(prompt);

        const s = await getSession(session_id);
        setCost(s.total_cost_rub || 0);

        setMessages((ms) => ms.filter((m) => m.kind !== "thinking"));
        const sections = prompt.expected_structure?.length ?? 0;
        push({
          role: "system",
          kind: "text",
          content: `Промт готов — ${prompt.full_prompt.length} символов, ${sections} разделов.\n\nСкопируйте и запустите внешний Deep Research, затем загрузите .md файл с результатами.`,
        });
        push({
          role: "system",
          kind: "ref",
          refKind: "prompt",
          title: "Research-промт",
          subtitle: `${sections} разделов · готов к копированию`,
          accent: true,
        });
        push({
          role: "system",
          kind: "dr-picker",
        });
        setArtifact({ kind: "prompt", data: prompt });
        setPhase(PHASE.PROMPT);
      } catch (e) {
        setMessages((ms) => ms.filter((m) => m.kind !== "thinking"));
        showToast(`Ошибка: ${e instanceof Error ? e.message : String(e)}`);
      } finally {
        setPending(false);
      }
    },
    [pending, sessionTitle, push]
  );

  const goToUploadStage = useCallback(() => {
    push({ role: "user", kind: "text", content: "Я уже запустил внешний DR" });
    push({
      role: "system",
      kind: "text",
      content:
        "Хорошо. Когда отчёты будут готовы — загружайте их. Поддерживаю .md, .txt — до 10 файлов за раз.",
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
      primary: "Выбрать файлы для загрузки →",
      action: "trigger-upload",
    });
    setArtifact({ kind: "upload-stage" });
    setPhase(PHASE.UPLOAD);
  }, [push]);

  // ===== DR picker handlers =====
  const runIntegratedDr = useCallback(
    async (service: AutoDRService) => {
      if (!sessionId) {
        showToast("Сессия не найдена — начните новый вопрос");
        return;
      }
      if (drBusy) return;
      setDrBusy(service);
      push({
        role: "user",
        kind: "text",
        content: `Запустить Deep Research через ${service}`,
      });
      push({
        role: "system",
        kind: "thinking",
        traces: [
          `${service}: формирую запрос`,
          "опрашиваю источники",
          "собираю результаты",
        ],
        onDone: () => {},
      });
      try {
        const res = await runAutoDR(sessionId, service, {
          prompt: promptData?.full_prompt,
        });
        setMessages((ms) => ms.filter((m) => m.kind !== "thinking"));
        const s = await getSession(sessionId);
        setCost(s.total_cost_rub || 0);
        push({
          role: "system",
          kind: "text",
          content: `${service}: ${res.source_count} источник(ов), $${res.cost_usd.toFixed(4)}. Файл «${res.filename}» добавлен в источники сессии.`,
        });
        push({
          role: "system",
          kind: "ref",
          refKind: "upload",
          title: res.filename,
          subtitle: `${res.source_count} источник(ов) · ${res.word_count} слов`,
          accent: true,
        });
        push({
          role: "system",
          kind: "cta",
          primary: "Перейти к анализу →",
          action: "go-upload-stage",
          secondary: "Загрузить ещё отчёт",
          secondaryAction: "go-upload-stage",
        });
        setPhase(PHASE.UPLOAD);
      } catch (e) {
        setMessages((ms) => ms.filter((m) => m.kind !== "thinking"));
        const msg = e instanceof Error ? e.message : String(e);
        showToast(`${service}: ${msg}`);
        push({
          role: "system",
          kind: "text",
          content: `${service} не сработал: ${msg}\n\nВыберите другой сервис ниже или загрузите .md вручную.`,
        });
      } finally {
        setDrBusy(null);
      }
    },
    [sessionId, drBusy, promptData, push]
  );

  const launchExternalDr = useCallback(
    (key: DrServiceKey, url: string) => {
      if (!promptData) {
        showToast("Промт ещё не готов");
        return;
      }
      try {
        navigator.clipboard.writeText(promptData.full_prompt);
      } catch (_) {}
      if (url && typeof window !== "undefined") {
        window.open(url, "_blank", "noopener,noreferrer");
      }
      showToast(
        `Промт скопирован — открыл ${key} в новой вкладке. Когда отчёт будет готов, загрузите .md.`
      );
      goToUploadStage();
    },
    [promptData, goToUploadStage]
  );

  const actUpload = useCallback(
    async (files: File[]) => {
      if (!sessionId) {
        showToast("Сессия не найдена — начните новый вопрос");
        return;
      }
      if (!files.length) return;
      push({
        role: "user",
        kind: "text",
        content: `Загружаю ${files.length} файл(ов): ${files.map((f) => f.name).join(", ")}`,
      });
      setPending(true);

      push({
        role: "system",
        kind: "thinking",
        traces: [
          `читаю ${files.length} файл(ов)`,
          "извлечение фактов и утверждений",
          "сверка между источниками",
          "поиск противоречий и пробелов",
        ],
        onDone: () => {},
      });

      try {
        await uploadReports(sessionId, files);
        const pref = getPipelineModel();
        const analysis = await analyze(sessionId, pref);
        setAnalysisData(analysis);

        const s = await getSession(sessionId);
        setCost(s.total_cost_rub || 0);

        setMessages((ms) => ms.filter((m) => m.kind !== "thinking"));

        const conflictsCount = analysis.conflicts.length;
        const gapsCount = analysis.gaps.length;
        const consensusCount = analysis.consensus.length;
        const unverifiedCount = analysis.unverified_numbers.length;

        push({
          role: "system",
          kind: "text",
          content: `Прочитал ${files.length} отчётов. Нашёл ${consensusCount} согласий, ${conflictsCount} противоречий, ${gapsCount} пробелов, ${unverifiedCount} неподтверждённых цифр.\n\nПротиворечия — главное. Разбираем?`,
        });
        push({
          role: "system",
          kind: "ref",
          refKind: "critique",
          title: "Критика и сверка",
          subtitle: `${consensusCount} · ${conflictsCount} · ${gapsCount} · ${unverifiedCount}`,
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
        setArtifact({ kind: "critique", data: analysis });
      } catch (e) {
        setMessages((ms) => ms.filter((m) => m.kind !== "thinking"));
        showToast(`Ошибка анализа: ${e instanceof Error ? e.message : String(e)}`);
      } finally {
        setPending(false);
      }
    },
    [sessionId, push]
  );

  const actTopup = useCallback(() => {
    push({
      role: "user",
      kind: "text",
      content: "Запускай followup — хочу закрыть пробелы",
    });
    const fu = analysisData?.followup_prompt;
    if (fu) {
      push({
        role: "system",
        kind: "text",
        content: `Followup-промт готов. Скопируйте его, запустите в DR, загрузите результат.`,
      });
      push({
        role: "system",
        kind: "ref",
        refKind: "topup",
        title: "Followup-промт",
        subtitle: `${fu.prompt.length.toLocaleString("ru-RU")} символов · ${fu.target_info || "готов к копированию"}`,
        accent: true,
      });
      setArtifact({ kind: "topup" });
    } else {
      push({
        role: "system",
        kind: "text",
        content: "Запустите ещё один DR по оставшимся пробелам и загрузите результат.",
      });
    }
    push({
      role: "system",
      kind: "cta",
      primary: "Выбрать followup-файл →",
      action: "trigger-followup",
    });
    setPhase(PHASE.TOPUP);
  }, [push, analysisData]);

  const actFollowup = useCallback(
    async (files: File[]) => {
      if (!sessionId) {
        showToast("Сессия не найдена");
        return;
      }
      if (!files.length) return;
      push({
        role: "user",
        kind: "text",
        content: `Загружаю followup: ${files.map((f) => f.name).join(", ")}`,
      });
      setPending(true);

      push({
        role: "system",
        kind: "thinking",
        traces: [
          "читаю followup-отчёт",
          "сверка с пробелами",
          "синтез финального отчёта",
          "проверка цитирования",
        ],
        onDone: () => {},
      });

      try {
        await uploadFollowup(sessionId, files);
        const pref = getPipelineModel();
        const final = await synthesize(sessionId, pref);
        setFinalData(final);

        const s = await getSession(sessionId);
        setCost(s.total_cost_rub || 0);

        setMessages((ms) => ms.filter((m) => m.kind !== "thinking"));
        push({
          role: "system",
          kind: "text",
          content: "Отчёт готов. Открыл справа — для экспорта кнопки в шапке.",
        });
        push({
          role: "system",
          kind: "ref",
          refKind: "report",
          title: final.executive_summary?.main_answer?.slice(0, 60) || "Финальный отчёт",
          subtitle: `${final.all_sources?.length ?? 0} источников · ₽ ${Math.round(s.total_cost_rub || 0)}`,
          accent: true,
        });
        setPhase(PHASE.DONE);
        setArtifact({ kind: "report", data: final });
      } catch (e) {
        setMessages((ms) => ms.filter((m) => m.kind !== "thinking"));
        showToast(`Ошибка синтеза: ${e instanceof Error ? e.message : String(e)}`);
      } finally {
        setPending(false);
      }
    },
    [sessionId, push]
  );

  const actFinal = useCallback(async () => {
    if (!sessionId) {
      showToast("Сессия не найдена");
      return;
    }
    setPending(true);
    push({
      role: "system",
      kind: "thinking",
      traces: [
        "сборка документа",
        "извлечение headline-цифр",
        "ранжирование факторов",
        "библиография",
        "финальная проверка цитирования",
      ],
      onDone: () => {},
    });

    try {
      const pref = getPipelineModel();
      const final = await synthesize(sessionId, pref);
      setFinalData(final);

      const s = await getSession(sessionId);
      setCost(s.total_cost_rub || 0);

      setMessages((ms) => ms.filter((m) => m.kind !== "thinking"));
      push({
        role: "system",
        kind: "text",
        content: "Отчёт готов. Открыл справа — для экспорта кнопки в шапке.",
      });
      push({
        role: "system",
        kind: "ref",
        refKind: "report",
        title: final.executive_summary?.main_answer?.slice(0, 60) || "Финальный отчёт",
        subtitle: `${final.all_sources?.length ?? 0} источников · ₽ ${Math.round(s.total_cost_rub || 0)}`,
        accent: true,
      });
      setPhase(PHASE.DONE);
      setArtifact({ kind: "report", data: final });
    } catch (e) {
      setMessages((ms) => ms.filter((m) => m.kind !== "thinking"));
      showToast(`Ошибка синтеза: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setPending(false);
    }
  }, [sessionId, push]);

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
      } else if (action === "trigger-upload") {
        uploadRef.current?.click();
      } else if (action === "go-topup") {
        actTopup();
      } else if (action === "trigger-followup") {
        followupRef.current?.click();
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
          "Вопрос принят. Используйте кнопки выше для следующих шагов — загрузки файлов и синтеза.",
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
    localStorage.removeItem("sr-session-id-v2");
    setMessages([INITIAL_MESSAGE]);
    setPhase(PHASE.START);
    setCost(0);
    setSessionTitle("Новая сессия");
    setSessionId(null);
    setPromptData(null);
    setAnalysisData(null);
    setFinalData(null);
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
    if (m.kind === "dr-picker") {
      return (
        <Msg key={m.id} role="system">
          <DrPicker
            onIntegrated={runIntegratedDr}
            onCopyLaunch={launchExternalDr}
            onSkip={goToUploadStage}
            disabled={pending}
            busyKey={drBusy}
          />
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
        title: "Research-промт",
        actions: (
          <>
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
        title: "Загрузка отчётов",
        actions: (
          <button
            className="icon-btn primary"
            onClick={() => uploadRef.current?.click()}
          >
            выбрать файлы
          </button>
        ),
      };
    }
    if (artifact.kind === "critique") {
      return {
        kind: "Критика",
        title: "Сверка источников",
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
    if (artifact.kind === "topup") {
      return {
        kind: "Добор",
        title: "Followup-промт",
        actions: (
          <>
            <button className="icon-btn primary" onClick={copyFollowupPrompt}>
              скопировать
            </button>
          </>
        ),
      };
    }
    if (artifact.kind === "report") {
      return {
        kind: "Отчёт",
        title: (finalData as FinalReport | null)?.executive_summary?.main_answer?.slice(0, 60) || "Финальный отчёт",
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
          </>
        ),
      };
    }
    return null;
  })();

  // ===== Source panel data — not applicable for real API (no numeric bibliography) =====
  const src = null;

  // ===== Render =====
  return (
    <div className="ws-root">
      {/* Hidden file inputs */}
      <input
        ref={uploadRef}
        type="file"
        multiple
        accept=".md,.txt"
        style={{ display: "none" }}
        onChange={(e) => {
          const files = Array.from(e.target.files || []);
          if (files.length) actUpload(files);
          e.target.value = "";
        }}
      />
      <input
        ref={followupRef}
        type="file"
        multiple
        accept=".md,.txt"
        style={{ display: "none" }}
        onChange={(e) => {
          const files = Array.from(e.target.files || []);
          if (files.length) actFollowup(files);
          e.target.value = "";
        }}
      />

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
          <ModelPicker compact />
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
                placeholder="Поиск по сессиям"
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
              const filtered = q
                ? savedSessions.filter(
                    (r) => r.raw_question.toLowerCase().includes(q)
                  )
                : savedSessions;
              if (!filtered.length) {
                return (
                  <div className="sb-empty">
                    {q ? "Ничего не найдено" : "Нет сессий"}
                  </div>
                );
              }
              return filtered.map((r) => {
                const isCurrent = r.session_id === sessionId;
                const dateLabel = r.created_at
                  ? new Date(r.created_at).toLocaleDateString("ru-RU", {
                      day: "2-digit", month: "short",
                    })
                  : "";
                const previewTitle =
                  r.raw_question.length > 50
                    ? r.raw_question.slice(0, 47) + "…"
                    : r.raw_question;
                const statusBadge =
                  r.status === "cancelled" ? "✕" :
                  r.has_final_report ? "✓" :
                  r.status === "analyzed" ? "·" :
                  "○";
                return (
                  <div
                    key={r.session_id}
                    className={"sb-session" + (isCurrent ? " current" : "")}
                  >
                    <button
                      className="sb-session-main"
                      title={r.raw_question}
                      onClick={() => loadSavedSession(r.session_id, previewTitle)}
                    >
                      <span className={"sb-session-dot" + (isCurrent ? " active" : "")}>
                        {statusBadge}
                      </span>
                      <span className="sb-session-title">{previewTitle}</span>
                      <span className="sb-session-meta">
                        {dateLabel} · ₽ {Math.round(r.total_cost_rub || 0)}
                      </span>
                    </button>
                    <button
                      className="sb-session-del"
                      title="Удалить сессию"
                      onClick={(e) => {
                        e.stopPropagation();
                        if (confirm(`Удалить сессию «${previewTitle}»?`)) {
                          deleteSavedSession(r.session_id);
                        }
                      }}
                    >
                      ✕
                    </button>
                  </div>
                );
              });
            })()}
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
                {pending && sessionId ? (
                  <button
                    type="button"
                    className="composer-send"
                    onClick={onCancel}
                    style={{ background: "var(--paper-2)", color: "var(--ink)", border: "1px solid var(--ink)" }}
                    title="Прервать запущенный шаг (за уже потраченные токены спишется)"
                  >
                    Отменить
                  </button>
                ) : (
                  <button
                    className="composer-send"
                    onClick={onSend}
                    disabled={!input.trim() || pending}
                  >
                    Отправить
                  </button>
                )}
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
              {artifact.kind === "prompt" && promptData && (
                <div className="prompt-doc">
                  <h1>Research-промт</h1>
                  <div className="prompt-subhead">
                    <span>{promptData.full_prompt.length.toLocaleString("ru-RU")} символов</span>
                    {promptData.expected_structure?.length ? (
                      <>
                        <span>·</span>
                        <span>{promptData.expected_structure.length} разделов</span>
                      </>
                    ) : null}
                  </div>
                  {promptData.reasoning && (
                    <div className="prompt-rec-block">
                      <div className="rec-label">Логика промта</div>
                      <p style={{ fontSize: 13, lineHeight: 1.55, color: "var(--ink-2)" }}>
                        {promptData.reasoning}
                      </p>
                    </div>
                  )}
                  <div className="prompt-section">
                    <pre
                      style={{
                        whiteSpace: "pre-wrap",
                        fontFamily: "var(--mono)",
                        fontSize: 12,
                        lineHeight: 1.6,
                        color: "var(--ink-2)",
                        background: "var(--paper-2)",
                        padding: "16px",
                        borderRadius: 4,
                        border: "1px solid var(--rule)",
                      }}
                    >
                      {promptData.full_prompt}
                    </pre>
                  </div>
                  {promptData.tips_for_search && (
                    <div className="prompt-section">
                      <div className="ps-title">Советы по поиску</div>
                      <p style={{ fontSize: 13, lineHeight: 1.55 }}>{promptData.tips_for_search}</p>
                    </div>
                  )}
                </div>
              )}
              {artifact.kind === "prompt" && !promptData && (
                <div style={{ padding: 24, color: "var(--ink-3)" }}>Промт не загружен</div>
              )}
              {(artifact.kind === "upload" || artifact.kind === "upload-stage") && (
                <div className="upload-doc">
                  <h1
                    style={{
                      fontSize: 22,
                      fontWeight: 700,
                      letterSpacing: "-0.015em",
                      margin: "0 0 6px 0",
                    }}
                  >
                    Загрузка отчётов
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
                    Запустите внешний DR по скопированному промту и возвращайтесь сюда
                  </div>
                  <label className="upload-dropzone" style={{ cursor: "pointer" }}>
                    <input
                      type="file"
                      multiple
                      accept=".md,.txt"
                      style={{ display: "none" }}
                      onChange={(e) => {
                        const files = Array.from(e.target.files || []);
                        if (files.length) actUpload(files);
                        e.target.value = "";
                      }}
                    />
                    <div className="big">
                      Нажмите чтобы выбрать файлы или перетащите сюда
                    </div>
                    <div className="small">
                      .md, .txt · до 10 файлов
                    </div>
                  </label>
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
                    <strong>Совет.</strong> Claude Research выгружает один .md файл.
                    Perplexity и OpenAI DR — .md или копия текста. Можно загружать несколько файлов сразу.
                  </div>
                </div>
              )}
              {artifact.kind === "topup" && analysisData?.followup_prompt && (
                <div className="prompt-doc">
                  <h1>Followup-промт</h1>
                  <div className="prompt-subhead">
                    <span>{analysisData.followup_prompt.prompt.length.toLocaleString("ru-RU")} символов</span>
                    <span>·</span>
                    <span>{analysisData.followup_prompt.intent}</span>
                    <span>·</span>
                    <span>{analysisData.followup_prompt.suggested_tool}</span>
                  </div>
                  {analysisData.followup_prompt.target_info && (
                    <div className="prompt-rec-block">
                      <div className="rec-label">Цель</div>
                      <p style={{ fontSize: 13, lineHeight: 1.55, color: "var(--ink-2)" }}>
                        {analysisData.followup_prompt.target_info}
                      </p>
                    </div>
                  )}
                  <div className="prompt-section">
                    <pre
                      style={{
                        whiteSpace: "pre-wrap",
                        fontFamily: "var(--mono)",
                        fontSize: 12,
                        lineHeight: 1.6,
                        color: "var(--ink-2)",
                        background: "var(--paper-2)",
                        padding: "16px",
                        borderRadius: 4,
                        border: "1px solid var(--rule)",
                      }}
                    >
                      {analysisData.followup_prompt.prompt}
                    </pre>
                  </div>
                </div>
              )}
              {artifact.kind === "topup" && !analysisData?.followup_prompt && (
                <div style={{ padding: 24, color: "var(--ink-3)" }}>Followup-промт не сгенерирован</div>
              )}
              {artifact.kind === "critique" && analysisData && (
                <CritiqueArtifact
                  analysisOutput={analysisData}
                  openSource={openSource}
                />
              )}
              {artifact.kind === "critique" && !analysisData && (
                <div style={{ padding: 24, color: "var(--ink-3)" }}>Анализ не загружен</div>
              )}
              {artifact.kind === "report" && finalData && (
                <>
                  {qualityGrade && qualityGrade.grade !== "N/A" && (
                    <div className={`quality-grade quality-grade--${qualityGrade.grade.toLowerCase()}`}>
                      <div className="quality-grade__head">
                        <span className="quality-grade__label">Quality</span>
                        <span className="quality-grade__letter">{qualityGrade.grade}</span>
                        <span className="quality-grade__score">{(qualityGrade.score * 100).toFixed(0)}/100</span>
                      </div>
                      <div className="quality-grade__summary">{qualityGrade.summary}</div>
                      <div className="quality-grade__metrics">
                        <span title="Источники с высокой надёжностью">
                          STRONG <b>{qualityGrade.strong_count}</b>/{qualityGrade.total_sources}
                        </span>
                        <span title="Уникальных доменов в библиографии">
                          доменов <b>{qualityGrade.unique_domains}</b>
                        </span>
                        <span title="Согласованные утверждения / противоречия / пробелы">
                          согл. <b>{qualityGrade.consensus_count}</b> · конф. <b>{qualityGrade.conflict_count}</b> · проб. <b>{qualityGrade.gap_count}</b>
                        </span>
                      </div>
                    </div>
                  )}
                  <ReportArtifact
                    finalReport={finalData}
                    openSource={openSource}
                  />
                </>
              )}
              {artifact.kind === "report" && !finalData && (
                <div style={{ padding: 24, color: "var(--ink-3)" }}>Отчёт не готов</div>
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
            <div>{String(src)}</div>
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
            <h4>Стоимость сессии</h4>
            <div className="popover-row total">
              <span>Итого</span>
              <span className="v">
                ₽ {cost.toFixed(2).replace(".", ",")}
              </span>
            </div>
            {sessionId && (
              <div className="popover-row">
                <span style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--ink-3)" }}>
                  session: {sessionId}
                </span>
              </div>
            )}
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
              <div className="export-group-label">Экспорт</div>
              {sessionId && (
                <>
                  <a
                    className="export-item"
                    href={`${process.env.NEXT_PUBLIC_V4_API_BASE || "http://localhost:8010"}/api/v4/sessions/${sessionId}/export?format=md`}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={() => setExportOpen(false)}
                  >
                    <span className="export-text">
                      <span className="export-name">Markdown</span>
                      <span className="export-meta">.md</span>
                    </span>
                  </a>
                  <a
                    className="export-item"
                    href={`${process.env.NEXT_PUBLIC_V4_API_BASE || "http://localhost:8010"}/api/v4/sessions/${sessionId}/export?format=docx`}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={() => setExportOpen(false)}
                  >
                    <span className="export-text">
                      <span className="export-name">Word Document</span>
                      <span className="export-meta">.docx</span>
                    </span>
                  </a>
                  <a
                    className="export-item"
                    href={`${process.env.NEXT_PUBLIC_V4_API_BASE || "http://localhost:8010"}/api/v4/sessions/${sessionId}/export?format=json`}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={() => setExportOpen(false)}
                  >
                    <span className="export-text">
                      <span className="export-name">Raw JSON</span>
                      <span className="export-meta">.json</span>
                    </span>
                  </a>
                </>
              )}
              {!sessionId && (
                <div style={{ padding: "8px 12px", color: "var(--ink-3)", fontSize: 12 }}>
                  Нет активной сессии
                </div>
              )}
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
