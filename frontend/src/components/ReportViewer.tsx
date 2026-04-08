"use client";

import { motion } from "framer-motion";
import {
  AlertTriangle,
  Download,
  FileCode2,
  FileSearch,
  FileText,
  Globe,
  ShieldCheck,
  TriangleAlert,
} from "lucide-react";

import {
  getDownloadUrl,
  type ArtifactsResponse,
  type EvidenceResponse,
  type SessionMeta,
  type SourcesResponse,
} from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

interface ReportViewerProps {
  session: SessionMeta;
  sessionId: string;
  evidence: EvidenceResponse | null;
  sources: SourcesResponse | null;
  artifacts: ArtifactsResponse | null;
}

function formatPercent(value: number): string {
  return `${Math.round((value || 0) * 100)}%`;
}

function formatScore(value: number): string {
  return value.toFixed(2);
}

function DownloadBar({ sessionId, formats }: { sessionId: string; formats: string[] }) {
  return (
    <div className="flex flex-wrap gap-2">
      {formats.map((format) => (
        <Button key={format} variant="outline" size="sm" asChild>
          <a href={getDownloadUrl(sessionId, format)} download>
            <Download className="mr-1.5 h-3.5 w-3.5" />
            {format.toUpperCase()}
          </a>
        </Button>
      ))}
    </div>
  );
}

function BriefTab({ session }: { session: SessionMeta }) {
  const brief = session.analysis_brief;
  const requestSpec = session.request_spec;
  const taskSpec = session.task_spec;

  if (!brief) {
    return (
      <Card>
        <CardContent className="p-6 text-sm text-muted-foreground">
          The analysis brief is not available yet.
        </CardContent>
      </Card>
    );
  }

  return (
    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
      <Card className="border-primary/15 bg-primary/5">
        <CardHeader>
          <CardTitle>{brief.title}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 text-sm text-muted-foreground">
          <p>{brief.executive_summary}</p>
          <div className="flex flex-wrap gap-2">
            <Badge variant={brief.recommendation_posture.includes("allowed") ? "success" : "warning"}>
              {brief.recommendation_posture}
            </Badge>
            <Badge variant="secondary">{session.audit_summary?.release_status ?? "pending"}</Badge>
          </div>
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-foreground">Key findings</p>
            <ul className="list-disc pl-5">
              {brief.key_findings.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-foreground">Uncertainty</p>
            <p>{brief.uncertainty_statement}</p>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Request Spec</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm text-muted-foreground">
            <p>Subject: {requestSpec?.subject ?? "n/a"}</p>
            <p>Report type: {requestSpec?.report_type?.replaceAll("_", " ") ?? "n/a"}</p>
            <p>Decision context: {requestSpec?.decision_context ?? "n/a"}</p>
            <p>Scope: {requestSpec?.geography ?? "n/a"} · {requestSpec?.time_horizon ?? "n/a"}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Task Frame</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm text-muted-foreground">
            <p>Budget cap: ${taskSpec?.max_budget_usd?.toFixed(2) ?? "0.00"}</p>
            <p>Evaluation dimensions: {(taskSpec?.evaluation_dimensions ?? []).join(", ") || "n/a"}</p>
            <p>Success criteria: {(taskSpec?.success_criteria ?? []).length}</p>
            <p>Actual spend: ${session.cost_usd.toFixed(2)}</p>
          </CardContent>
        </Card>
      </div>
    </motion.div>
  );
}

function ReportTab({ session, sessionId }: { session: SessionMeta; sessionId: string }) {
  const formats = Object.keys(session.report_urls ?? {});
  const htmlUrl = session.report_urls?.html;
  const report = session.report;

  return (
    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
      <DownloadBar sessionId={sessionId} formats={formats} />

      {htmlUrl ? (
        <div className="overflow-hidden rounded-2xl border bg-white">
          <iframe src={htmlUrl} title="HTML report" className="h-[70vh] w-full" />
        </div>
      ) : (
        <Card>
          <CardContent className="space-y-5 p-6">
            <div>
              <h2 className="text-xl font-semibold">{report?.title ?? session.title ?? "Report"}</h2>
              <p className="mt-2 text-sm text-muted-foreground">
                {report?.executive_summary ?? session.analysis_brief?.executive_summary ?? "No rendered report yet."}
              </p>
            </div>
            {report?.sections?.map((section) => (
              <div key={section.title} className="space-y-2">
                <h3 className="text-base font-medium">{section.title}</h3>
                <div className="whitespace-pre-wrap text-sm text-muted-foreground">{section.content}</div>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </motion.div>
  );
}

function EvidenceTab({ evidence }: { evidence: EvidenceResponse | null }) {
  if (!evidence) {
    return (
      <Card>
        <CardContent className="p-6 text-sm text-muted-foreground">Evidence artifacts are not available yet.</CardContent>
      </Card>
    );
  }

  return (
    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardContent className="p-5">
            <p className="text-xs uppercase tracking-wide text-muted-foreground">Coverage</p>
            <p className="mt-2 text-2xl font-semibold">{formatPercent(evidence.coverage_report.coverage_ratio)}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-5">
            <p className="text-xs uppercase tracking-wide text-muted-foreground">Covered Questions</p>
            <p className="mt-2 text-2xl font-semibold">
              {evidence.coverage_report.covered_questions}/{evidence.coverage_report.total_questions}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-5">
            <p className="text-xs uppercase tracking-wide text-muted-foreground">Strong Sources</p>
            <p className="mt-2 text-2xl font-semibold">{formatPercent(evidence.coverage_report.strong_source_ratio)}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-5">
            <p className="text-xs uppercase tracking-wide text-muted-foreground">Contradictions</p>
            <p className="mt-2 text-2xl font-semibold">{evidence.coverage_report.contradiction_count}</p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Question Coverage</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm text-muted-foreground">
          {evidence.coverage_report.questions.map((question) => (
            <div key={question.question_id} className="rounded-xl border p-4">
              <div className="flex flex-wrap items-center gap-2">
                <p className="font-medium text-foreground">{question.question}</p>
                <Badge variant={question.status === "covered" ? "success" : "warning"}>{question.status}</Badge>
              </div>
              <p className="mt-2">
                {question.evidence_count} evidence items · {question.source_count} source links
              </p>
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Claim Table</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {evidence.claim_table.map((claim) => (
            <div key={claim.claim_id} className="rounded-xl border p-4">
              <div className="flex flex-wrap items-center gap-2">
                <p className="text-sm font-medium text-foreground">{claim.statement}</p>
                <Badge variant={claim.recommendation_safe ? "success" : "secondary"}>
                  {claim.recommendation_safe ? "safe" : "bounded"}
                </Badge>
                <Badge variant="outline">confidence {formatScore(claim.confidence)}</Badge>
              </div>
              <p className="mt-2 text-xs text-muted-foreground">
                Evidence: {claim.supporting_evidence_ids.join(", ")} · Sources: {claim.source_ids.join(", ")}
              </p>
              {claim.contradiction_notes.length > 0 ? (
                <div className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">
                  {claim.contradiction_notes.join(" ")}
                </div>
              ) : null}
            </div>
          ))}
        </CardContent>
      </Card>
    </motion.div>
  );
}

function SourcesTab({ sources }: { sources: SourcesResponse | null }) {
  if (!sources) {
    return (
      <Card>
        <CardContent className="p-6 text-sm text-muted-foreground">Source ledger is not available yet.</CardContent>
      </Card>
    );
  }

  return (
    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="space-y-3">
      {sources.sources.map((source) => (
        <Card key={source.source_id}>
          <CardContent className="flex items-start justify-between gap-4 p-5">
            <div className="min-w-0 space-y-2">
              <a
                href={source.url}
                target="_blank"
                rel="noreferrer"
                className="block truncate text-sm font-medium text-primary hover:underline"
              >
                {source.title}
              </a>
              <p className="text-xs text-muted-foreground">
                {source.domain} · {source.source_type.replaceAll("_", " ")} · score {formatScore(source.reliability_score)}
              </p>
              <p className="text-sm text-muted-foreground">{source.selection_reason}</p>
            </div>
            <a href={source.url} target="_blank" rel="noreferrer" className="shrink-0">
              <Globe className="h-4 w-4 text-muted-foreground" />
            </a>
          </CardContent>
        </Card>
      ))}
    </motion.div>
  );
}

function GapsRisksTab({ session, evidence }: { session: SessionMeta; evidence: EvidenceResponse | null }) {
  const brief = session.analysis_brief;
  const audit = session.audit_summary;
  const gaps = evidence?.coverage_report.gaps ?? session.coverage_report?.gaps ?? [];

  return (
    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <TriangleAlert className="h-4 w-4 text-amber-600" />
              Gaps
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm text-muted-foreground">
            {gaps.length > 0 ? (
              <ul className="list-disc pl-5">
                {gaps.map((gap) => (
                  <li key={gap}>{gap}</li>
                ))}
              </ul>
            ) : (
              <p>No coverage gaps recorded.</p>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <AlertTriangle className="h-4 w-4 text-rose-600" />
              Risks
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm text-muted-foreground">
            {(brief?.key_risks ?? []).length > 0 ? (
              <ul className="list-disc pl-5">
                {(brief?.key_risks ?? []).map((risk) => (
                  <li key={risk}>{risk}</li>
                ))}
              </ul>
            ) : (
              <p>No explicit risk list recorded.</p>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Audit Results</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 text-sm text-muted-foreground">
          <div className="flex flex-wrap gap-2">
            <Badge variant={audit?.release_status === "released" ? "success" : "warning"}>
              {audit?.release_status ?? "pending"}
            </Badge>
            <Badge variant="secondary">{audit?.checks_passed ?? 0} passed</Badge>
            <Badge variant={audit?.checks_failed ? "warning" : "secondary"}>
              {audit?.checks_failed ?? 0} failed
            </Badge>
          </div>

          {(brief?.limitations ?? []).length > 0 ? (
            <div>
              <p className="mb-2 font-medium text-foreground">Limitations</p>
              <ul className="list-disc pl-5">
                {(brief?.limitations ?? []).map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          ) : null}

          {(audit?.failures ?? []).length > 0 ? (
            <div>
              <p className="mb-2 font-medium text-foreground">Failures</p>
              <ul className="list-disc pl-5 text-destructive">
                {(audit?.failures ?? []).map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          ) : null}

          {(audit?.warnings ?? []).length > 0 ? (
            <div>
              <p className="mb-2 font-medium text-foreground">Warnings</p>
              <ul className="list-disc pl-5">
                {(audit?.warnings ?? []).map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </CardContent>
      </Card>
    </motion.div>
  );
}

function DataTab({
  session,
  evidence,
  artifacts,
}: {
  session: SessionMeta;
  evidence: EvidenceResponse | null;
  artifacts: ArtifactsResponse | null;
}) {
  return (
    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <FileSearch className="h-4 w-4" />
              Package Files
            </CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            <ul className="list-disc pl-5">
              {(artifacts?.package_files ?? []).map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <ShieldCheck className="h-4 w-4" />
              Run Artifacts
            </CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            <ul className="list-disc pl-5">
              {(artifacts?.artifacts ?? []).map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <ShieldCheck className="h-4 w-4" />
              Spend Ledger
            </CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            {(session.spend_breakdown ?? []).length > 0 ? (
              <ul className="list-disc pl-5">
                {(session.spend_breakdown ?? []).map((item) => (
                  <li key={item.entry_id}>
                    {item.stage}: ${item.cost_usd.toFixed(3)} via {item.provider}/{item.model}
                  </li>
                ))}
              </ul>
            ) : (
              <p>No spend ledger recorded yet.</p>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <FileSearch className="h-4 w-4" />
              Materials
            </CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            {(session.materials ?? []).length > 0 ? (
              <ul className="list-disc pl-5">
                {(session.materials ?? []).map((item) => (
                  <li key={item.material_id}>
                    {item.title} ({item.kind}, {item.text_length} chars)
                  </li>
                ))}
              </ul>
            ) : (
              <p>No user materials were attached.</p>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <FileCode2 className="h-4 w-4" />
            Structured Output
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <pre className="overflow-x-auto rounded-xl bg-muted p-4 text-xs leading-6 text-muted-foreground">
            {JSON.stringify(
              {
                request_spec: session.request_spec,
                task_spec: session.task_spec,
                depth_profile: session.depth_profile,
                spend_breakdown: session.spend_breakdown,
                materials: session.materials,
                handoff_prompts: session.handoff_prompts,
                analysis_brief: session.analysis_brief,
                coverage_report: session.coverage_report,
                audit_summary: session.audit_summary,
                claim_count: evidence?.claim_table.length ?? 0,
                evidence_count: evidence?.evidence_ledger.length ?? 0,
              },
              null,
              2,
            )}
          </pre>
        </CardContent>
      </Card>
    </motion.div>
  );
}

export function ReportViewer({ session, sessionId, evidence, sources, artifacts }: ReportViewerProps) {
  return (
    <Tabs defaultValue="brief" className="space-y-6">
      <TabsList className="h-auto w-full flex-wrap justify-start gap-2 rounded-2xl bg-muted/70 p-2">
        <TabsTrigger value="brief" className="gap-2 rounded-xl">
          <FileText className="h-4 w-4" />
          Brief
        </TabsTrigger>
        <TabsTrigger value="report" className="gap-2 rounded-xl">
          <FileText className="h-4 w-4" />
          Report
        </TabsTrigger>
        <TabsTrigger value="evidence" className="gap-2 rounded-xl">
          <ShieldCheck className="h-4 w-4" />
          Evidence
        </TabsTrigger>
        <TabsTrigger value="sources" className="gap-2 rounded-xl">
          <Globe className="h-4 w-4" />
          Sources
        </TabsTrigger>
        <TabsTrigger value="gaps" className="gap-2 rounded-xl">
          <TriangleAlert className="h-4 w-4" />
          Gaps & Risks
        </TabsTrigger>
        <TabsTrigger value="data" className="gap-2 rounded-xl">
          <FileCode2 className="h-4 w-4" />
          Data
        </TabsTrigger>
      </TabsList>

      <TabsContent value="brief">
        <BriefTab session={session} />
      </TabsContent>
      <TabsContent value="report">
        <ReportTab session={session} sessionId={sessionId} />
      </TabsContent>
      <TabsContent value="evidence">
        <EvidenceTab evidence={evidence} />
      </TabsContent>
      <TabsContent value="sources">
        <SourcesTab sources={sources} />
      </TabsContent>
      <TabsContent value="gaps">
        <GapsRisksTab session={session} evidence={evidence} />
      </TabsContent>
      <TabsContent value="data">
        <DataTab session={session} evidence={evidence} artifacts={artifacts} />
      </TabsContent>
    </Tabs>
  );
}
