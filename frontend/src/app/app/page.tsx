"use client";

import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  Download,
  FileText,
  Loader2,
  Plus,
  Trash2,
} from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type ReportSummary = {
  session_id: string;
  title: string;
  status: string;
  created_at: string;
  cost_usd: number;
  verdict: string | null;
  output_formats: string[];
};

const API_BASE = "/api";

function formatDate(value: string): string {
  try {
    return new Intl.DateTimeFormat("ru-RU", {
      day: "2-digit",
      month: "long",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(value));
  } catch {
    return value;
  }
}

function formatCost(value: number): string {
  return new Intl.NumberFormat("ru-RU", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
  }).format(value || 0);
}

function getStatusMeta(report: ReportSummary) {
  if (report.status === "failed") {
    return {
      label: "Ошибка",
      className: "bg-rose-100 text-rose-700 border border-rose-200",
    };
  }

  if (report.status === "awaiting_handoff") {
    return {
      label: "Нужно действие",
      className: "bg-amber-100 text-amber-700 border border-amber-200",
    };
  }

  if (report.verdict === "PASS" || report.status === "completed") {
    return {
      label: "Готов",
      className: "bg-emerald-100 text-emerald-700 border border-emerald-200",
    };
  }

  return {
    label: "Генерируется",
    className: "bg-sky-100 text-sky-700 border border-sky-200",
  };
}

function SkeletonCard() {
  return (
    <Card className="animate-pulse">
      <CardHeader className="space-y-3">
        <div className="h-5 w-3/4 rounded bg-muted" />
        <div className="h-4 w-1/2 rounded bg-muted" />
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="h-6 w-24 rounded-full bg-muted" />
          <div className="h-4 w-16 rounded bg-muted" />
        </div>
        <div className="grid grid-cols-3 gap-2">
          <div className="h-10 rounded bg-muted" />
          <div className="h-10 rounded bg-muted" />
          <div className="h-10 rounded bg-muted" />
        </div>
      </CardContent>
    </Card>
  );
}

function EmptyState() {
  return (
    <Card className="overflow-hidden border-dashed">
      <CardContent className="flex min-h-[360px] flex-col items-center justify-center px-6 py-16 text-center">
        <div className="mb-6 flex h-24 w-24 items-center justify-center rounded-[2rem] bg-primary/10">
          <FileText className="h-12 w-12 text-primary/60" />
        </div>
        <h2 className="text-2xl font-semibold tracking-tight">Ваши отчёты</h2>
        <p className="mt-3 max-w-md text-sm leading-6 text-muted-foreground">
          Здесь появятся все собранные аналитические отчёты. Начните с первого запроса,
          и система подготовит документ, слайды и визуализации.
        </p>
        <Link href="/app/new" className="mt-6">
          <Button>
            <Plus className="mr-2 h-4 w-4" />
            Создайте первый отчёт
          </Button>
        </Link>
      </CardContent>
    </Card>
  );
}

export default function DashboardPage() {
  const [reports, setReports] = useState<ReportSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  async function loadReports() {
    try {
      const response = await fetch(`${API_BASE}/reports`, { cache: "no-store" });
      if (!response.ok) {
        throw new Error(`Failed to fetch reports: ${response.status}`);
      }
      const data = (await response.json()) as ReportSummary[];
      setReports(data);
    } catch (error) {
      console.error(error);
      setReports([]);
    } finally {
      setLoading(false);
    }
  }

  async function deleteReport(sessionId: string) {
    try {
      setDeletingId(sessionId);
      const response = await fetch(`${API_BASE}/reports/${sessionId}`, {
        method: "DELETE",
      });
      if (!response.ok) {
        throw new Error(`Failed to delete report: ${response.status}`);
      }
      setReports((current) => current.filter((report) => report.session_id !== sessionId));
    } catch (error) {
      console.error(error);
    } finally {
      setDeletingId(null);
    }
  }

  useEffect(() => {
    loadReports();
  }, []);

  const content = useMemo(() => {
    if (loading) {
      return (
        <div className="grid gap-4 md:grid-cols-2">
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </div>
      );
    }

    if (reports.length === 0) {
      return <EmptyState />;
    }

    return (
      <div className="grid gap-4 md:grid-cols-2">
        {reports.map((report, index) => {
          const statusMeta = getStatusMeta(report);
          return (
            <motion.div
              key={report.session_id}
              initial={{ opacity: 0, y: 18 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.05, duration: 0.25 }}
            >
              <Card className="h-full overflow-hidden border-border/80">
                <CardHeader className="space-y-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <CardTitle className="line-clamp-2 text-lg leading-6">
                        {report.title}
                      </CardTitle>
                      <p className="mt-2 text-sm text-muted-foreground">
                        {formatDate(report.created_at)}
                      </p>
                    </div>
                    <span
                      className={`shrink-0 rounded-full px-3 py-1 text-xs font-medium ${statusMeta.className}`}
                    >
                      {statusMeta.label}
                    </span>
                  </div>
                </CardHeader>

                <CardContent className="space-y-5">
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">Стоимость</span>
                    <span className="font-medium">{formatCost(report.cost_usd)}</span>
                  </div>

                  <div className="grid grid-cols-3 gap-2">
                    <Button asChild variant="default" size="sm">
                      <Link href={`/app/reports/${report.session_id}`}>View</Link>
                    </Button>

                    <Button asChild variant="outline" size="sm">
                      <a
                        href={`${API_BASE}/reports/${report.session_id}/download/pdf`}
                        download
                      >
                        <Download className="mr-1.5 h-3.5 w-3.5" />
                        PDF
                      </a>
                    </Button>

                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => deleteReport(report.session_id)}
                      disabled={deletingId === report.session_id}
                    >
                      {deletingId === report.session_id ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <>
                          <Trash2 className="mr-1.5 h-3.5 w-3.5" />
                          Delete
                        </>
                      )}
                    </Button>
                  </div>
                </CardContent>
              </Card>
            </motion.div>
          );
        })}
      </div>
    );
  }, [deletingId, loading, reports]);

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Ваши отчёты</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            История всех сгенерированных документов, слайдов и материалов.
          </p>
        </div>

        <Link href="/app/new">
          <Button>
            <Plus className="mr-2 h-4 w-4" />
            Новый отчёт
          </Button>
        </Link>
      </div>

      {content}
    </div>
  );
}
