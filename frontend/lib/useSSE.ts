"use client";

import { useEffect, useRef } from "react";

export type SSEEvent = {
  event: string;
  message: string;
  ts?: number;
  [k: string]: any;
};

/**
 * Poll-based progress hook. Railway's HTTP/2 proxy drops long-lived SSE
 * connections (ERR_HTTP2_PROTOCOL_ERROR), so we poll /events?since=<cursor>
 * instead. The `url` contract is preserved: pass the /stream URL and we'll
 * derive the /events URL from it.
 */
export function useSSE(
  url: string | null,
  opts: { onEvent: (ev: SSEEvent) => void }
) {
  const cbRef = useRef(opts.onEvent);
  cbRef.current = opts.onEvent;

  useEffect(() => {
    if (!url) return;
    const eventsUrl = url.replace(/\/stream$/, "/events");
    let cursor = 0;
    let cancelled = false;
    let timer: any = null;

    const tick = async () => {
      if (cancelled) return;
      try {
        const res = await fetch(`${eventsUrl}?since=${cursor}`, {
          cache: "no-store",
        });
        if (res.ok) {
          const body = await res.json();
          cursor = body.cursor ?? cursor;
          for (const ev of body.events || []) {
            cbRef.current(ev as SSEEvent);
          }
          if (body.status === "done" || body.status === "error") {
            cbRef.current({ event: "close", message: body.status });
            return;
          }
        }
      } catch (err) {
        cbRef.current({ event: "error", message: "poll failed" });
      }
      if (!cancelled) timer = setTimeout(tick, 1500);
    };
    tick();

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [url]);
}
