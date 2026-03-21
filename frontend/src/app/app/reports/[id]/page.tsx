"use client";

import { useMemo } from "react";
import { useParams } from "next/navigation";
import { motion } from "framer-motion";
import {
  ArrowLeft,
  Download,
  ExternalLink,
  FileImage,
  FileText,
  Globe,
  Loader2,
  Presentation,
} from "lucide-react";
import Link from "next/link";
import { CostTracker } from "@/components/CostTracker";
import { ReportProgress } from "@/components/ReportProgress";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useReport } from "@/hooks/useReport";
import { useSSE } from "@/hooks/useSSE";
import { getDownloadUrl, type ReportData, type SessionMeta } from "@/lib/api";

type ReportMetadata = Record<string, unknown>;

function asString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === "string" && item.length > 0);
}

function extractChartNames(metadata: ReportMetadata): string[] {
  const direct = asStringArray(metadata.charts);
  if (direct.length > 0) return direct;

  const available = asStringArray(metadata.available_charts);
  if (available.length > 0) return available;

  const chartObjects = Array.isArray(metadata.chart_paths) ? metadata.chart_paths : [];
  return chartObjects
    .map((item) => (typeof item === "string" ? item.split(/[\\/]/).pop() ?? "" : ""))
    .filter(Boolean);
}

function extractHtmlUrl(session: SessionMeta | null): string | null {
  return session?.report_urls?.html ?? null;
}

function extractPdfUrl(session: SessionMeta | null): string | null {
  return session?.report_urls?.pdf ?? null;
}

function extractPresentationInfo(report: ReportData | null, session: SessionMeta | null) {
  const metadata = (report?.metadata ?? {}) as ReportMetadata;
  const presentationUrl =
    asString(metadata.presentation_url) ??
    asString(metadata.gamma_url) ??
    asString(metadata.slides_url) ??
    session?.report_urls?.presentation ??
    null;
  const presentationPath =
    asString(metadata.presentation_path) ?? asString(metadata.pptx_path) ?? null;

  return { presentationUrl, presentationPath };
}

function PDFViewer({ src }: { src: string }) {
  return (
    <div className="overflow-hidden rounded-2xl border bg-white">
      <iframe
        src={src}
        title="PDF viewer"
        className="h-[70vh] w-full"
      />
    </div>
  );
}

function HtmlViewer({ src }: { src: string }) {
  return (
    <div className="overflow-hidden rounded-2xl border bg-white">
      <iframe
        src={src}
        title="HTML report"
        className="h-[70vh] w-full"
      />
    </div>
  );
}

function DocumentTab({
  report,
  session,
  sessionId,
}: {
  report: ReportData;
  session: SessionMeta | null;
  sessionId: string;
}) {
  const pdfUrl = extractPdfUrl(session);
  const htmlUrl = extractHtmlUrl(session);

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      className="space-y-6"
    >
      <div className="flex flex-wrap gap-3">
        {["pdf", "docx", "html"].map((format) => (
          <Button key={format} variant="outline" asChild>
            <a href={getDownloadUrl(sessionId, format)} download>
              <Download className="mr-2 h-4 w-4" />
              {format.toUpperCase()}
            </a>
          </Button>
        ))}
      </div>

      <Card className="border-primary/10 bg-primary/5">
        <CardHeader>
          <CardTitle className="text-sm uppercase tracking-[0.2em] text-primary">
            Executive Summary
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm leading-7 text-foreground/90">
            {report.executive_summary}
          </p>
        </CardContent>
      </Card>

      {pdfUrl ? (
        <PDFViewer src={pdfUrl} />
      ) : htmlUrl ? (
        <HtmlViewer src={htmlUrl} />
      ) : (
        <Card>
          <CardContent className="flex min-h-[320px] items-center justify-center text-center text-sm text-muted-foreground">
            Документ ещё не готов для предпросмотра.
          </CardContent>
        </Card>
      )}
    </motion.div>
  );
}

function SlidesTab({
  report,
  session,
  sessionId,
}: {
  report: ReportData;
  session: SessionMeta | null;
  sessionId: string;
}) {
  const { presentationUrl, presentationPath } = extractPresentationInfo(report, session);
  const presentationDownloadUrl = session?.report_urls?.presentation ?? getDownloadUrl(sessionId, "pptx");

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      className="space-y-6"
    >
      {presentationUrl && /^https?:\/\//.test(presentationUrl) ? (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <Button variant="outline" asChild>
              <a href={presentationUrl} target="_blank" rel="noreferrer">
                <ExternalLink className="mr-2 h-4 w-4" />
                Открыть презентацию
              </a>
            </Button>
          </div>
          <div className="overflow-hidden rounded-2xl border bg-white">
            <iframe
              src={presentationUrl}
              title="Slides viewer"
              className="h-[70vh] w-full"
            />
          </div>
        </div>
      ) : presentationPath ? (
        <Card>
          <CardContent className="flex min-h-[280px] flex-col items-center justify-center gap-4 text-center">
            <Presentation className="h-12 w-12 text-muted-foreground/40" />
            <div className="space-y-2">
              <p className="text-base font-medium">PPTX готов к скачиванию</p>
              <p className="text-sm text-muted-foreground">
                Онлайн-предпросмотр недоступен, но файл уже собран.
              </p>
            </div>
            <Button asChild>
              <a href={presentationDownloadUrl} download>
                <Download className="mr-2 h-4 w-4" />
                Скачать PPTX
              </a>
            </Button>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="flex min-h-[280px] flex-col items-center justify-center gap-3 text-center">
            <Presentation className="h-12 w-12 text-muted-foreground/35" />
            <p className="text-sm text-muted-foreground">
              Презентация генерируется...
            </p>
          </CardContent>
        </Card>
      )}
    </motion.div>
  );
}

function DataTab({
  report,
  sessionId,
}: {
  report: ReportData;
  sessionId: string;
}) {
  const metadata = (report.metadata ?? {}) as ReportMetadata;
  const chartNames = extractChartNames(metadata);

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      className="space-y-6"
    >
      {chartNames.length === 0 ? (
        <Card>
          <CardContent className="flex min-h-[260px] flex-col items-center justify-center gap-3 text-center">
            <FileImage className="h-12 w-12 text-muted-foreground/35" />
            <p className="text-sm text-muted-foreground">
              Графики ещё не доступны.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-6">
          {chartNames.map((chartName) => {
              const chartUrl = `/api/reports/${sessionId}/charts/${chartName}`;
            return (
              <Card key={chartName}>
                <CardHeader className="flex flex-row items-center justify-between">
                  <CardTitle className="text-base">{chartName}</CardTitle>
                  <Button variant="ghost" size="sm" asChild>
                    <a href={chartUrl} target="_blank" rel="noreferrer">
                      <ExternalLink className="h-4 w-4" />
                    </a>
                  </Button>
                </CardHeader>
                <CardContent>
                  <img
                    src={chartUrl}
                    alt={chartName}
                    className="w-full rounded-xl border bg-white object-contain"
                  />
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Metadata</CardTitle>
        </CardHeader>
        <CardContent>
          <pre className="overflow-x-auto rounded-xl bg-muted p-4 text-xs leading-6 text-muted-foreground">
            {JSON.stringify(metadata, null, 2)}
          </pre>
        </CardContent>
      </Card>
    </motion.div>
  );
}

function SourcesTab({ report }: { report: ReportData }) {
  const sources = useMemo(() => {
    const items = report.sections.flatMap((section) =>
      section.sources.map((url) => ({
        url,
        section: section.title,
      }))
    );
    return Array.from(new Map(items.map((item) => [item.url, item])).values());
  }, [report.sections]);

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      className="space-y-4"
    >
      {sources.length === 0 ? (
        <Card>
          <CardContent className="flex min-h-[260px] flex-col items-center justify-center gap-3 text-center">
            <Globe className="h-12 w-12 text-muted-foreground/35" />
            <p className="text-sm text-muted-foreground">Источники ещё не отображены.</p>
          </CardContent>
        </Card>
      ) : (
        sources.map((source) => (
          <Card key={source.url}>
            <CardContent className="flex items-start justify-between gap-4 p-5">
              <div className="min-w-0 space-y-2">
                <a
                  href={source.url}
                  target="_blank"
                  rel="noreferrer"
                  className="block truncate text-sm font-medium text-primary hover:underline"
                >
                  {source.url}
                </a>
                <p className="text-xs text-muted-foreground">
                  Использован в разделе: {source.section}
                </p>
              </div>
              <Badge variant="secondary">Source</Badge>
            </CardContent>
          </Card>
        ))
      )}
    </motion.div>
  );
}

function CompletedReport({
  report,
  session,
  sessionId,
}: {
  report: ReportData;
  session: SessionMeta | null;
  sessionId: string;
}) {
  return (
    <Tabs defaultValue="document" className="space-y-6">
      <TabsList className="h-auto w-full flex-wrap justify-start gap-2 rounded-2xl bg-muted/70 p-2">
        <TabsTrigger value="document" className="gap-2 rounded-xl">
          <FileText className="h-4 w-4" />
          Document
        </TabsTrigger>
        <TabsTrigger value="slides" className="gap-2 rounded-xl">
          <Presentation className="h-4 w-4" />
          Slides
        </TabsTrigger>
        <TabsTrigger value="data" className="gap-2 rounded-xl">
          <FileImage className="h-4 w-4" />
          Data
        </TabsTrigger>
        <TabsTrigger value="sources" className="gap-2 rounded-xl">
          <Globe className="h-4 w-4" />
          Sources
        </TabsTrigger>
      </TabsList>

      <TabsContent value="document">
        <DocumentTab report={report} session={session} sessionId={sessionId} />
      </TabsContent>
      <TabsContent value="slides">
        <SlidesTab report={report} session={session} sessionId={sessionId} />
      </TabsContent>
      <TabsContent value="data">
        <DataTab report={report} sessionId={sessionId} />
      </TabsContent>
      <TabsContent value="sources">
        <SourcesTab report={report} />
      </TabsContent>
    </Tabs>
  );
}

export default function ReportPage() {
  const params = useParams<{ id: string }>();
  const { session, report, status, loading } = useReport(params.id);
  const sse = useSSE(status !== "completed" && status !== "failed" ? params.id : null);

  const isComplete = status === "completed" || sse.isComplete;
  const isFailed = status === "failed" || sse.isFailed;
  const isRunning = !isComplete && !isFailed;

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35 }}
      className="space-y-6"
    >
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Link href="/app">
            <Button variant="ghost" size="icon" className="shrink-0">
              <ArrowLeft className="h-4 w-4" />
            </Button>
          </Link>
          <div>
            <h1 className="text-xl font-bold tracking-tight">
              {report?.title || "Report"}
            </h1>
            {session && (
              <p className="font-mono text-xs text-muted-foreground">
                {session.session_id}
              </p>
            )}
          </div>
        </div>
        <CostTracker cost={session?.cost_usd ?? sse.costUsd} />
      </div>

      {isRunning && (
        <Card>
          <CardContent className="p-6">
            <ReportProgress
              steps={sse.steps}
              currentStep={sse.currentStep}
              sessionId={params.id}
            />
          </CardContent>
        </Card>
      )}

      {isFailed && (
        <Card className="border-destructive/30 bg-destructive/5">
          <CardContent className="p-6 text-center">
            <p className="text-sm text-destructive">
              {sse.error || "Report generation failed"}
            </p>
          </CardContent>
        </Card>
      )}

      {isComplete && report && (
        <CompletedReport report={report} session={session} sessionId={params.id} />
      )}

      {isComplete && !report && (
        <Card>
          <CardContent className="p-8 text-center">
            <p className="text-muted-foreground">
              Отчёт завершён, но данные ещё не подгрузились.
            </p>
            <Button
              variant="outline"
              className="mt-4"
              onClick={() => window.location.reload()}
            >
              Reload
            </Button>
          </CardContent>
        </Card>
      )}
    </motion.div>
  );
}
