"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowLeft, Loader2 } from "lucide-react";

import { CostTracker } from "@/components/CostTracker";
import { ReportProgress } from "@/components/ReportProgress";
import { ReportViewer } from "@/components/ReportViewer";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useReport } from "@/hooks/useReport";
import { useSSE } from "@/hooks/useSSE";
import {
  getReportArtifacts,
  getReportEvidence,
  getReportSources,
  type ArtifactsResponse,
  type EvidenceResponse,
  type SourcesResponse,
} from "@/lib/api";

export default function ReportPage() {
  const params = useParams<{ id: string }>();
  const runId = params.id;
  const { session, report, status, loading, refetch } = useReport(runId);
  const sse = useSSE(status !== "completed" && status !== "failed" ? runId : null);

  const [evidence, setEvidence] = useState<EvidenceResponse | null>(null);
  const [sources, setSources] = useState<SourcesResponse | null>(null);
  const [artifacts, setArtifacts] = useState<ArtifactsResponse | null>(null);
  const [artifactError, setArtifactError] = useState<string | null>(null);

  const isComplete = status === "completed" || sse.isComplete;
  const isFailed = status === "failed" || sse.isFailed;
  const isRunning = !isComplete && !isFailed;

  useEffect(() => {
    if (!runId) return;
    if (!session && !isComplete && !isFailed) return;

    let active = true;
    void Promise.all([
      getReportEvidence(runId).catch(() => null),
      getReportSources(runId).catch(() => null),
      getReportArtifacts(runId).catch(() => null),
    ])
      .then(([nextEvidence, nextSources, nextArtifacts]) => {
        if (!active) return;
        setEvidence(nextEvidence);
        setSources(nextSources);
        setArtifacts(nextArtifacts);
        setArtifactError(null);
      })
      .catch((error) => {
        if (!active) return;
        setArtifactError(error instanceof Error ? error.message : "Failed to load artifacts");
      });

    return () => {
      active = false;
    };
  }, [runId, session, isComplete, isFailed]);

  useEffect(() => {
    if (!runId) return;
    if (!sse.isComplete && !sse.isFailed) return;
    void refetch();
  }, [refetch, runId, sse.isComplete, sse.isFailed]);

  const title = useMemo(
    () => session?.analysis_brief?.title ?? report?.title ?? session?.title ?? "Report",
    [report?.title, session?.analysis_brief?.title, session?.title],
  );
  const failureMessage =
    session?.audit_summary?.failures?.[0] ??
    "This run failed before the report package was assembled. Refreshing will not fix a backend execution error.";

  if (loading && !session) {
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
            <h1 className="text-xl font-bold tracking-tight">{title}</h1>
            {session ? (
              <p className="font-mono text-xs text-muted-foreground">{session.session_id}</p>
            ) : null}
          </div>
        </div>
        <CostTracker cost={session?.cost_usd ?? sse.costUsd} maxBudget={session?.task_spec?.max_budget_usd ?? 2} />
      </div>

      {isRunning ? (
        <Card>
          <CardContent className="p-6">
            <ReportProgress steps={sse.steps} currentStep={sse.currentStep} sessionId={runId} />
          </CardContent>
        </Card>
      ) : null}

      {isFailed && session?.audit_summary?.failures?.length ? (
        <Card className="border-destructive/30 bg-destructive/5">
          <CardContent className="space-y-3 p-6 text-sm text-destructive">
            <p>This run failed closed. Audit blockers:</p>
            <ul className="list-disc pl-5">
              {session.audit_summary.failures.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}

      {artifactError ? (
        <Card className="border-dashed">
          <CardContent className="p-6 text-sm text-muted-foreground">{artifactError}</CardContent>
        </Card>
      ) : null}

      {session && (session.report || session.analysis_brief) ? (
        <ReportViewer
          session={session}
          sessionId={runId}
          evidence={evidence}
          sources={sources}
          artifacts={artifacts}
        />
      ) : isFailed ? (
        <Card className="border-destructive/30 bg-destructive/5">
          <CardContent className="space-y-3 p-8 text-center">
            <p className="font-medium text-destructive">This run failed before the report package was materialized.</p>
            <p className="text-sm text-muted-foreground">{failureMessage}</p>
            <Button variant="outline" className="mt-2" onClick={() => void refetch()}>
              Refresh
            </Button>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="p-8 text-center">
            <p className="text-muted-foreground">
              Run metadata is available, but the report package has not been materialized yet.
            </p>
            <Button variant="outline" className="mt-4" onClick={() => void refetch()}>
              Refresh
            </Button>
          </CardContent>
        </Card>
      )}
    </motion.div>
  );
}
