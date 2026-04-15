"use client";

import { useEffect, useRef } from "react";

export type SSEEvent = {
  event: string;
  message: string;
  ts?: number;
  [k: string]: any;
};

export function useSSE(
  url: string | null,
  opts: { onEvent: (ev: SSEEvent) => void }
) {
  const cbRef = useRef(opts.onEvent);
  cbRef.current = opts.onEvent;

  useEffect(() => {
    if (!url) return;
    const es = new EventSource(url);
    const names = [
      "message",
      "planner",
      "scout",
      "analyst",
      "bisociator",
      "summarizer",
      "deepen",
      "add-domain",
      "connect",
      "status",
      "done",
      "error",
      "close",
    ];
    const handler = (evName: string) => (e: MessageEvent) => {
      let parsed: any = { event: evName, message: e.data };
      try {
        parsed = { event: evName, ...JSON.parse(e.data) };
      } catch {}
      cbRef.current(parsed as SSEEvent);
    };
    const listeners = names.map((n) => {
      const h = handler(n);
      es.addEventListener(n, h as any);
      return [n, h] as const;
    });
    es.onerror = () => {
      cbRef.current({ event: "error", message: "SSE connection lost" });
    };
    return () => {
      listeners.forEach(([n, h]) => es.removeEventListener(n, h as any));
      es.close();
    };
  }, [url]);
}
