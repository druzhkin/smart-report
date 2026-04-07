"use client";

import { useEffect, useState, useCallback } from "react";
import { type SessionMeta, type ReportData, getReport } from "@/lib/api";

export function useReport(id: string) {
  const [session, setSession] = useState<SessionMeta | null>(null);
  const [report, setReport] = useState<ReportData | null>(null);
  const [status, setStatus] = useState<string>("pending");
  const [loading, setLoading] = useState(true);

  const fetchReport = useCallback(async () => {
    if (!id) {
      setLoading(false);
      return;
    }
    try {
      const data = await getReport(id);
      setSession(data);
      setReport(data.report);
      setStatus(data.status);
    } catch {
      setStatus("failed");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    if (!id) {
      setLoading(false);
      return;
    }
    fetchReport();
  }, [fetchReport]);

  useEffect(() => {
    if (loading) return;
    if (status === "completed" || status === "failed") return;

    const intervalId = setInterval(() => {
      void fetchReport();
    }, 5000);

    return () => clearInterval(intervalId);
  }, [fetchReport, loading, status]);

  return { session, report, status, loading, refetch: fetchReport };
}
