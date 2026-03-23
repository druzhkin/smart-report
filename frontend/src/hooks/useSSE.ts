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

  const retriesRef = useRef(0);
  const terminalRef = useRef(false);

  const processEvent = useCallback((event: SSEEvent) => {
    const displayKey = STEP_MAPPING[event.step];
    if (!displayKey && event.step !== "complete" && event.step !== "pipeline") return;

    if (typeof event.cost_usd === "number") setCostUsd(event.cost_usd);
    if (typeof event.tokens_used === "number") setTokensUsed(event.tokens_used);

    if ((event.step === "complete") || (event.status === "done" && event.step === "pipeline")) {
      terminalRef.current = true;
      setIsComplete(true);
      if (event.report_urls) setReportUrls(event.report_urls);
      setSteps((prev) => prev.map((s) => ({ ...s, status: "done" as const, completedAt: Date.now() })));
      return;
    }

    if (event.status === "error") {
      terminalRef.current = true;
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
    terminalRef.current = false;
    retriesRef.current = 0;
    setSteps(DISPLAY_STEPS.map((s) => ({ ...s, status: "pending" as const })));
    setCurrentStep(null);
    setIsComplete(false);
    setIsFailed(false);
    setCostUsd(0);
    setTokensUsed(0);
    setReportUrls(null);
    setError(null);

    if (!sessionId) return;

    let cancelled = false;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let abortController: AbortController | null = null;
    const decoder = new TextDecoder();

    const processBuffer = (buffer: string): string => {
      let remaining = buffer;

      while (true) {
        const separatorIndex = remaining.search(/\r?\n\r?\n/);
        if (separatorIndex === -1) break;

        const block = remaining.slice(0, separatorIndex);
        remaining = remaining.slice(separatorIndex).replace(/^\r?\n\r?\n/, "");

        const data = block
          .split(/\r?\n/)
          .filter((line) => line.startsWith("data:"))
          .map((line) => line.slice(5).trim())
          .join("\n");

        if (!data) continue;

        try {
          retriesRef.current = 0;
          processEvent(JSON.parse(data) as SSEEvent);
        } catch {
          // Ignore malformed frames and keep the stream alive.
        }
      }

      return remaining;
    };

    const scheduleReconnect = () => {
      if (cancelled || terminalRef.current) return;

      if (retriesRef.current >= 5) {
        setError("Connection lost");
        return;
      }

      retriesRef.current += 1;
      reconnectTimer = setTimeout(connect, 1000 * Math.pow(2, retriesRef.current));
    };

    const connect = async () => {
      if (cancelled || terminalRef.current) return;

      abortController = new AbortController();

      try {
        const response = await fetch(getStreamUrl(sessionId), {
          headers: { Accept: "text/event-stream" },
          cache: "no-store",
          signal: abortController.signal,
        });

        if (!response.ok || !response.body) {
          throw new Error(`Failed to connect to stream: ${response.status}`);
        }

        const reader = response.body.getReader();
        let buffer = "";

        while (!cancelled) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          buffer = processBuffer(buffer);
        }

        buffer += decoder.decode();
        processBuffer(buffer);

        if (!terminalRef.current) {
          scheduleReconnect();
        }
      } catch {
        if (!cancelled && !terminalRef.current) {
          scheduleReconnect();
        }
      }
    };

    void connect();

    return () => {
      cancelled = true;
      abortController?.abort();
      if (reconnectTimer) clearTimeout(reconnectTimer);
    };
  }, [sessionId, processEvent]);

  return { steps, currentStep, isComplete, isFailed, costUsd, tokensUsed, reportUrls, error };
}
