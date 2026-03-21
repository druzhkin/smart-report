"use client";

import { useEffect, useState, useCallback } from "react";
import { type SessionMeta, type ReportData, getReport } from "@/lib/api";

export function useReport(id: string) {
  const [session, setSession] = useState<SessionMeta | null>(null);
  const [report, setReport] = useState<ReportData | null>(null);
  const [status, setStatus] = useState<string>("pending");
  const [loading, setLoading] = useState(true);

  const fetchReport = useCallback(async () => {
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
    fetchReport();
  }, [fetchReport]);

  return { session, report, status, loading, refetch: fetchReport };
}
