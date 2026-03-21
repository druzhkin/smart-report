"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { getStreamUrl, type SSEEvent } from "@/lib/api";

export interface PipelineStep {
  key: string;
  label: string;
  status: "pending" | "active" | "done" | "error";
  startedAt?: number;
  completedAt?: number;
  message?: string;
}

const STEP_LABELS: Record<string, string> = {
  intake: "Analyzing Request",
  cost_guard: "Budget Check",
  prompt_router: "Routing Model",
  prompt_king: "Building Prompt",
  prompt_splitter: "Splitting Sections",
  supervisor: "Orchestrating",
  research: "Deep Research",
  summarization: "Summarizing",
  reflect: "Quality Reflection",
  citation_verifier: "Verifying Citations",
  research_critique: "Research Critique",
  viz_agent: "Creating Visualizations",
  render_and_present: "Rendering Report",
  qa: "Final QA",
  save_to_knowledge_library: "Saving to Library",
  complete: "Complete",
};

const DISPLAY_STEPS = [
  { key: "intake", label: "Intake" },
  { key: "planning", label: "Planning" },
  { key: "research", label: "Research" },
  { key: "reflection", label: "Review" },
  { key: "visualization", label: "Charts" },
  { key: "rendering", label: "Rendering" },
  { key: "qa", label: "Final QA" },
];

const STEP_MAPPING: Record<string, string> = {
  intake: "intake",
  cost_guard: "planning",
  prompt_router: "planning",
  prompt_king: "planning",
  prompt_splitter: "planning",
  supervisor: "planning",
  research: "research",
  summarization: "research",
  reflect: "reflection",
  citation_verifier: "reflection",
  research_critique: "reflection",
  viz_agent: "visualization",
  render_and_present: "rendering",
  qa: "qa",
  save_to_knowledge_library: "qa",
};

interface UseSSEReturn {
  steps: PipelineStep[];
  currentStep: string | null;
  isComplete: boolean;
  isFailed: boolean;
  costUsd: number;
  tokensUsed: number;
  reportUrls: Record<string, string> | null;
  error: string | null;
}

export function useSSE(sessionId: string | null): UseSSEReturn {
  const [steps, setSteps] = useState<PipelineStep[]>(() =>
    DISPLAY_STEPS.map((s) => ({ ...s, status: "pending" as const }))
  );
  const [currentStep, setCurrentStep] = useState<string | null>(null);
  const [isComplete, setIsComplete] = useState(false);
  const [isFailed, setIsFailed] = useState(false);
  const [costUsd, setCostUsd] = useState(0);
  const [tokensUsed, setTokensUsed] = useState(0);
  const [reportUrls, setReportUrls] = useState<Record<string, string> | null>(null);
  const [error, setError] = useState<string | null>(null);

  const esRef = useRef<EventSource | null>(null);
  const retriesRef = useRef(0);

  const processEvent = useCallback((event: SSEEvent) => {
    const displayKey = STEP_MAPPING[event.step];
    if (!displayKey && event.step !== "complete" && event.step !== "pipeline") return;

    if (event.cost_usd) setCostUsd(event.cost_usd);
    if (event.tokens_used) setTokensUsed(event.tokens_used);

    if (event.step === "complete" || event.status === "done" && event.step === "pipeline") {
      setIsComplete(true);
      if (event.report_urls) setReportUrls(event.report_urls);
      setSteps((prev) => prev.map((s) => ({ ...s, status: "done" as const, completedAt: Date.now() })));
      return;
    }

    if (event.status === "error") {
      setIsFailed(true);
      setError(event.message);
      return;
    }

    if (!displayKey) return;

    setCurrentStep(displayKey);

    setSteps((prev) =>
      prev.map((s) => {
        if (s.key === displayKey) {
          if (event.status === "started" && s.status !== "done") {
            return { ...s, status: "active", startedAt: s.startedAt || Date.now(), message: STEP_LABELS[event.step] };
          }
          if (event.status === "done") {
            return { ...s, status: "done", completedAt: Date.now(), message: STEP_LABELS[event.step] };
          }
        }
        return s;
      })
    );

    if (event.status === "started") {
      setSteps((prev) => {
        const idx = prev.findIndex((s) => s.key === displayKey);
        return prev.map((s, i) => {
          if (i < idx && s.status === "pending") {
            return { ...s, status: "done", completedAt: Date.now() };
          }
          return s;
        });
      });
    }
  }, []);

  useEffect(() => {
    if (!sessionId) return;

    const connect = () => {
      const es = new EventSource(getStreamUrl(sessionId));
      esRef.current = es;

      es.onmessage = (e) => {
        try {
          retriesRef.current = 0;
          const data: SSEEvent = JSON.parse(e.data);
          processEvent(data);
        } catch {
          // ignore parse errors
        }
      };

      es.onerror = () => {
        es.close();
        if (retriesRef.current < 5) {
          retriesRef.current++;
          setTimeout(connect, 1000 * Math.pow(2, retriesRef.current));
        } else {
          setError("Connection lost");
        }
      };
    };

    connect();

    return () => {
      esRef.current?.close();
    };
  }, [sessionId, processEvent]);

  return { steps, currentStep, isComplete, isFailed, costUsd, tokensUsed, reportUrls, error };
}
