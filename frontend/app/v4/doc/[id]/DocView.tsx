"use client";

/**
 * DocView — Swiss/Helvetica institutional document interface for v4.
 * One vertical document scroll through 6 states:
 *   START → PROMPT → UPLOAD → CRITIQUE → TOPUP → FINAL
 */

import { useState, useEffect, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import {
  getSession,
  generatePrompt,
  uploadReports,
  analyze,
  uploadFollowup,
  synthesize,
  exportUrl,
  type V4Session,
  type V4SessionStatus,
  type FinalSource,
} from "@/lib/apiV4";
import { useCost } from "@/lib/costContext";
import { DocTopbar } from "./DocTopbar";
import { SectionStart } from "./SectionStart";
import { SectionPrompt } from "./SectionPrompt";
import { SectionUpload } from "./SectionUpload";
import { SectionCritique } from "./SectionCritique";
import { SectionTopup } from "./SectionTopup";
import { SectionFinal } from "./SectionFinal";
import { SourceSidepanel } from "./SourceSidepanel";

/** Derive step number (1-6) from session status */
function statusToStep(status: V4SessionStatus): number {
  switch (status) {
    case "created":          return 1;
    case "prompt_ready":     return 2;
    case "reports_uploaded": return 3;
    case "analyzed":         return 4;
    case "dobor_uploaded":   return 5;
    case "synthesized":      return 6;
    default:                 return 1;
  }
}

export interface SourceEntry {
  n: number;
  title: string;
  origin: string;
  url: string;
}

interface SidepanelState {
  open: boolean;
  source: SourceEntry | null;
}

export function DocView({ sessionId }: { sessionId: string }) {
  const router = useRouter();
  const { setCost } = useCost();

  const [session, setSession] = useState<V4Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Per-section working states
  const [generatingPrompt, setGeneratingPrompt] = useState(false);
  const [uploadingReports, setUploadingReports] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [uploadingFollowup, setUploadingFollowup] = useState(false);
  const [synthesizing, setSynthesizing] = useState(false);

  // UI state
  const [sidepanel, setSidepanel] = useState<SidepanelState>({ open: false, source: null });
  const [activeSection, setActiveSection] = useState<string>("start");
  const [showExportMenu, setShowExportMenu] = useState(false);

  // Section refs for autoscroll
  const scrollRef = useRef<HTMLDivElement>(null);
  const sectionRefs = useRef<Record<string, HTMLElement | null>>({});

  // Load session on mount
  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const s = await getSession(sessionId);
        if (!cancelled) {
          setSession(s);
          setCost(s.total_cost_rub);
          setLoading(false);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Ошибка загрузки сессии");
          setLoading(false);
        }
      }
    }
    load();
    return () => { cancelled = true; };
  }, [sessionId, setCost]);

  // Autoscroll helper
  const scrollToSection = useCallback((id: string) => {
    const el = sectionRefs.current[id];
    if (el && scrollRef.current) {
      el.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, []);

  // Track active section via IntersectionObserver
  useEffect(() => {
    const root = scrollRef.current;
    if (!root) return;
    const obs = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) {
            setActiveSection(e.target.id.replace("vd-sec-", ""));
          }
        }
      },
      { root, rootMargin: "-10% 0% -70% 0%", threshold: 0 }
    );
    Object.values(sectionRefs.current).forEach((el) => { if (el) obs.observe(el); });
    return () => obs.disconnect();
  }, [session?.status]);

  // -- Action handlers --

  async function handleGeneratePrompt() {
    if (!session) return;
    setGeneratingPrompt(true);
    try {
      const prompt = await generatePrompt(session.session_id);
      const updated = { ...session, research_prompt: prompt, status: "prompt_ready" as V4SessionStatus };
      setSession(updated);
      setCost(updated.total_cost_rub);
      setTimeout(() => scrollToSection("prompt"), 300);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка генерации промта");
    } finally {
      setGeneratingPrompt(false);
    }
  }

  async function handleUploadReports(files: File[]) {
    if (!session) return;
    setUploadingReports(true);
    try {
      const uploaded = await uploadReports(session.session_id, files);
      const updated = { ...session, source_reports: uploaded, status: "reports_uploaded" as V4SessionStatus };
      setSession(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка загрузки файлов");
    } finally {
      setUploadingReports(false);
    }
  }

  async function handleAnalyze() {
    if (!session) return;
    setAnalyzing(true);
    try {
      await analyze(session.session_id);
      const freshSession = await getSession(session.session_id);
      setSession(freshSession);
      setCost(freshSession.total_cost_rub);
      setTimeout(() => scrollToSection("critique"), 300);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка анализа");
    } finally {
      setAnalyzing(false);
    }
  }

  async function handleUploadFollowup(files: File[]) {
    if (!session) return;
    setUploadingFollowup(true);
    try {
      const uploaded = await uploadFollowup(session.session_id, files);
      const updated = { ...session, followup_reports: uploaded, status: "dobor_uploaded" as V4SessionStatus };
      setSession(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка загрузки дополнений");
    } finally {
      setUploadingFollowup(false);
    }
  }

  async function handleSynthesize() {
    if (!session) return;
    setSynthesizing(true);
    try {
      await synthesize(session.session_id);
      const freshSession = await getSession(session.session_id);
      setSession(freshSession);
      setCost(freshSession.total_cost_rub);
      // When synthesized, isFinal becomes true and SectionFinal replaces the scroll view
      // No autoscroll needed — layout change is visible immediately
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка синтеза");
    } finally {
      setSynthesizing(false);
    }
  }

  function openSource(n: number) {
    if (!session?.final_report) return;
    const sources: FinalSource[] = session.final_report.all_sources || [];
    const src = sources[n - 1];
    setSidepanel({
      open: true,
      source: src
        ? { n, title: src.title, origin: src.origin, url: src.url }
        : { n, title: `Источник ${n}`, origin: "—", url: "" },
    });
  }

  function closeSidepanel() {
    setSidepanel((s) => ({ ...s, open: false }));
  }

  function handleExport(format: string) {
    const url = exportUrl(sessionId, format);
    window.open(url, "_blank");
    setShowExportMenu(false);
  }

  const step = session ? statusToStep(session.status) : 1;

  function registerRef(id: string) {
    return (el: HTMLElement | null) => { sectionRefs.current[id] = el; };
  }

  if (loading) {
    return (
      <div className="v4-doc" style={{ display: "flex", alignItems: "center", justifyContent: "center", minHeight: "100vh" }}>
        <div>
          <div className="vd-dots">
            <div className="vd-dot" />
            <div className="vd-dot" />
            <div className="vd-dot" />
          </div>
        </div>
      </div>
    );
  }

  if (error && !session) {
    return (
      <div className="v4-doc" style={{ display: "flex", alignItems: "center", justifyContent: "center", minHeight: "100vh" }}>
        <div style={{ textAlign: "center" }}>
          <div style={{ color: "var(--vd-bad)", fontFamily: "var(--vd-f-mono)", marginBottom: 16 }}>{error}</div>
          <button className="vd-btn-secondary" onClick={() => router.push("/v4/doc")}>
            ← Новое исследование
          </button>
        </div>
      </div>
    );
  }

  if (!session) return null;

  const isFinal = session.status === "synthesized";

  return (
    <div className="v4-doc">
      <DocTopbar
        question={session.raw_question}
        step={step}
        cost={session.total_cost_rub}
        onExport={() => setShowExportMenu((v) => !v)}
        onNewSession={() => router.push("/v4/doc")}
      />

      {showExportMenu && (
        <>
          <div
            style={{ position: "fixed", inset: 0, zIndex: 80 }}
            onClick={() => setShowExportMenu(false)}
          />
          <div className="vd-export-menu">
            {[
              { format: "pdf", label: "PDF" },
              { format: "docx", label: "Word (.docx)" },
              { format: "md", label: "Markdown" },
              { format: "json", label: "JSON (данные)" },
            ].map(({ format, label }) => (
              <button
                key={format}
                className="vd-export-item"
                onClick={() => handleExport(format)}
              >
                {label}
              </button>
            ))}
          </div>
        </>
      )}

      {isFinal ? (
        /* Final report has its own 3-col layout */
        <SectionFinal
          session={session}
          onCiteClick={openSource}
          onExport={() => setShowExportMenu((v) => !v)}
        />
      ) : (
        <div className="vd-scroll" ref={scrollRef}>
          <div className="vd-inner">
            {error && (
              <div style={{
                background: "var(--vd-accent-soft)",
                borderLeft: "3px solid var(--vd-bad)",
                padding: "10px 14px",
                marginBottom: 24,
                fontFamily: "var(--vd-f-mono)",
                fontSize: 12,
                color: "var(--vd-bad)"
              }}>
                {error}
                <button
                  style={{ marginLeft: 16, cursor: "pointer", background: "none", border: "none", color: "var(--vd-ink-3)", fontSize: 11 }}
                  onClick={() => setError(null)}
                >
                  ✕
                </button>
              </div>
            )}

            {/* Section 01 — START */}
            <div id="vd-sec-start" ref={registerRef("start")}>
              <SectionStart
                question={session.raw_question}
                loading={generatingPrompt}
                canProceed={step >= 1}
                alreadyDone={step > 1}
                onGenerate={handleGeneratePrompt}
              />
            </div>

            {/* Section 02 — PROMPT */}
            {step >= 2 && (
              <div id="vd-sec-prompt" ref={registerRef("prompt")}>
                <SectionPrompt
                  session={session}
                />
              </div>
            )}

            {/* Section 03 — UPLOAD */}
            {step >= 2 && (
              <div id="vd-sec-upload" ref={registerRef("upload")}>
                <SectionUpload
                  session={session}
                  uploading={uploadingReports}
                  analyzing={analyzing}
                  onUpload={handleUploadReports}
                  onAnalyze={handleAnalyze}
                />
              </div>
            )}

            {/* Section 04 — CRITIQUE */}
            {step >= 4 && (
              <div id="vd-sec-critique" ref={registerRef("critique")}>
                <SectionCritique session={session} />
              </div>
            )}

            {/* Section 05 — TOPUP */}
            {step >= 4 && (
              <div id="vd-sec-topup" ref={registerRef("topup")}>
                <SectionTopup
                  session={session}
                  uploading={uploadingFollowup}
                  synthesizing={synthesizing}
                  onUpload={handleUploadFollowup}
                  onSynthesize={handleSynthesize}
                />
              </div>
            )}
          </div>
        </div>
      )}

      <SourceSidepanel
        open={sidepanel.open}
        source={sidepanel.source}
        onClose={closeSidepanel}
      />
    </div>
  );
}
