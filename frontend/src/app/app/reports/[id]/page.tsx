"use client";

import { type ChangeEvent, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowLeft, Copy, Loader2, Play } from "lucide-react";

import { CostTracker } from "@/components/CostTracker";
import { ReportProgress } from "@/components/ReportProgress";
import { ReportViewer } from "@/components/ReportViewer";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { useReport } from "@/hooks/useReport";
import { useSSE } from "@/hooks/useSSE";
import {
  addTextMaterial,
  getReportArtifacts,
  getReportEvidence,
  getReportSources,
  resumeReport,
  uploadMaterial,
  type ArtifactsResponse,
  type EvidenceResponse,
  type SourcesResponse,
} from "@/lib/api";

export default function ReportPage() {
  const params = useParams<{ id: string }>();
  const runId = params.id;
  const { session, report, status, loading, refetch } = useReport(runId);
  const sse = useSSE(status !== "completed" && status !== "failed" && status !== "awaiting_handoff" ? runId : null);

  const [evidence, setEvidence] = useState<EvidenceResponse | null>(null);
  const [sources, setSources] = useState<SourcesResponse | null>(null);
  const [artifacts, setArtifacts] = useState<ArtifactsResponse | null>(null);
  const [artifactError, setArtifactError] = useState<string | null>(null);
  const [materialTitle, setMaterialTitle] = useState("");
  const [materialText, setMaterialText] = useState("");
  const [materialBusy, setMaterialBusy] = useState(false);
  const [handoffBusy, setHandoffBusy] = useState(false);
  const [handoffError, setHandoffError] = useState<string | null>(null);

  const isComplete = status === "completed" || sse.isComplete;
  const isFailed = status === "failed" || sse.isFailed;
  const isAwaitingHandoff = status === "awaiting_handoff";
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

  const handleCopy = async (value: string) => {
    await navigator.clipboard.writeText(value);
  };

  const handleAddMaterial = async () => {
    if (!runId || !materialText.trim()) return;
    setMaterialBusy(true);
    setHandoffError(null);
    try {
      await addTextMaterial(runId, {
        title: materialTitle.trim() || "Manual research notes",
        content: materialText,
        kind: "external_research",
      });
      setMaterialTitle("");
      setMaterialText("");
      await refetch();
    } catch (error) {
      setHandoffError(error instanceof Error ? error.message : "Failed to add material");
    } finally {
      setMaterialBusy(false);
    }
  };

  const handleUpload = async (event: ChangeEvent<HTMLInputElement>) => {
    const nextFile = event.target.files?.[0];
    if (!nextFile || !runId) return;
    setMaterialBusy(true);
    setHandoffError(null);
    try {
      await uploadMaterial(runId, nextFile, { kind: "external_research" });
      event.target.value = "";
      await refetch();
    } catch (error) {
      setHandoffError(error instanceof Error ? error.message : "Failed to upload material");
    } finally {
      setMaterialBusy(false);
    }
  };

  const handleResume = async () => {
    if (!runId) return;
    setHandoffBusy(true);
    setHandoffError(null);
    try {
      await resumeReport(runId);
      await refetch();
    } catch (error) {
      setHandoffError(error instanceof Error ? error.message : "Failed to resume report");
    } finally {
      setHandoffBusy(false);
    }
  };

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

      {isAwaitingHandoff ? (
        <Card className="border-primary/20 bg-primary/5">
          <CardContent className="space-y-6 p-6">
            <div className="space-y-2">
              <p className="text-lg font-semibold">Perplexity handoff is ready</p>
              <p className="text-sm text-muted-foreground">
                This run is intentionally paused. Use one or more prompts below in your Perplexity subscription, paste the results or upload
                files, then resume the report. If we auto-continued here, the “money-saving” mode would be fake.
              </p>
            </div>

            <div className="space-y-4">
              {(session?.handoff_prompts ?? []).map((prompt) => (
                <Card key={prompt.prompt_id}>
                  <CardContent className="space-y-3 p-4">
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <p className="font-medium">{prompt.title}</p>
                        <p className="mt-1 text-sm text-muted-foreground">{prompt.rationale}</p>
                      </div>
                      <Button variant="outline" size="sm" onClick={() => void handleCopy(prompt.prompt)}>
                        <Copy className="mr-2 h-4 w-4" />
                        Copy
                      </Button>
                    </div>
                    <pre className="overflow-x-auto rounded-xl bg-muted p-4 text-xs leading-6 text-muted-foreground">
                      {prompt.prompt}
                    </pre>
                  </CardContent>
                </Card>
              ))}
            </div>

            <Card>
              <CardContent className="space-y-4 p-4">
                <p className="font-medium">Add your own materials</p>
                <Textarea
                  value={materialText}
                  onChange={(event) => setMaterialText(event.target.value)}
                  placeholder="Paste Perplexity Deep Research output, internal notes, client context, or excerpts from your own docs."
                  className="min-h-[180px]"
                />
                <div className="flex flex-wrap gap-3">
                  <input
                    type="text"
                    value={materialTitle}
                    onChange={(event) => setMaterialTitle(event.target.value)}
                    placeholder="Material title"
                    className="min-w-[220px] rounded-md border bg-background px-3 py-2 text-sm"
                  />
                  <input type="file" onChange={handleUpload} className="text-sm" />
                  <Button variant="outline" onClick={handleAddMaterial} disabled={!materialText.trim() || materialBusy}>
                    {materialBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                    Add text material
                  </Button>
                </div>

                {(session?.materials ?? []).length > 0 ? (
                  <div className="rounded-xl border p-3 text-sm text-muted-foreground">
                    <p className="mb-2 font-medium text-foreground">Attached materials</p>
                    <ul className="list-disc pl-5">
                      {(session?.materials ?? []).map((material) => (
                        <li key={material.material_id}>
                          {material.title} ({material.kind}, {material.text_length} chars)
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}

                {handoffError ? <p className="text-sm text-destructive">{handoffError}</p> : null}

                <div className="flex justify-end">
                  <Button onClick={handleResume} disabled={handoffBusy}>
                    {handoffBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}
                    Resume run
                  </Button>
                </div>
              </CardContent>
            </Card>
          </CardContent>
        </Card>
      ) : null}

      {isRunning && !isAwaitingHandoff ? (
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
      ) : isAwaitingHandoff ? null : isFailed ? (
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
