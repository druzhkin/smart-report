"use client";

import { useEffect, useRef, useState } from "react";
import { v3GetEvents, type V3Event } from "./apiV3";

/**
 * Long-poll /api/research/{id}/events?since=<cursor> against v3 API.
 * Each response wakes after up to 25s or when the server has new events.
 */
export function useV3Events(jobId: string | null) {
  const [events, setEvents] = useState<V3Event[]>([]);
  const [status, setStatus] = useState<
    "pending" | "running" | "done" | "error" | "idle"
  >("idle");
  const [error, setError] = useState<string | null>(null);
  const cursorRef = useRef(0);
  const cancelledRef = useRef(false);

  useEffect(() => {
    if (!jobId) return;
    cancelledRef.current = false;
    cursorRef.current = 0;
    setEvents([]);
    setStatus("pending");
    setError(null);

    const loop = async () => {
      while (!cancelledRef.current) {
        try {
          const body = await v3GetEvents(jobId, cursorRef.current);
          cursorRef.current = body.cursor;
          if (body.events.length > 0) {
            setEvents((prev) => [...prev, ...body.events]);
          }
          setStatus(body.status);
          if (body.error) setError(body.error);
          if (body.status === "done" || body.status === "error") return;
        } catch (err: unknown) {
          setError(err instanceof Error ? err.message : "poll failed");
          // brief backoff before retrying
          await new Promise((r) => setTimeout(r, 2000));
        }
      }
    };

    loop();
    return () => {
      cancelledRef.current = true;
    };
  }, [jobId]);

  return { events, status, error };
}
