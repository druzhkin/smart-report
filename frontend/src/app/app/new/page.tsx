"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  FileText,
  Loader2,
  SearchCheck,
  ShieldCheck,
  Waypoints,
} from "lucide-react";

import { ClarifyingQuestions } from "@/components/ClarifyingQuestions";
import { ReportProgress } from "@/components/ReportProgress";
import { VoiceInput } from "@/components/VoiceInput";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Textarea } from "@/components/ui/textarea";
import { useReport } from "@/hooks/useReport";
import { useSSE } from "@/hooks/useSSE";
import {
  createReport,
  getClarificationPack,
  getReportPricing,
  scopeReport,
  type ClarificationPack,
  type PricingTier,
  type RequestSpec,
} from "@/lib/api";
import { formatCost } from "@/lib/utils";

type Depth = "light" | "standard" | "deep" | "exhaustive";

const DEPTHS: { value: Depth; label: string; desc: string }[] = [
  { value: "light", label: "Light", desc: "Quick orientation" },
  { value: "standard", label: "Standard", desc: "Balanced decision memo" },
  { value: "deep", label: "Deep", desc: "Broader source coverage" },
  { value: "exhaustive", label: "Exhaustive", desc: "Highest effort" },
];

const FORMATS = [
  { value: "pdf", label: "PDF" },
  { value: "html", label: "HTML" },
  { value: "docx", label: "DOCX" },
  { value: "pptx", label: "PPTX" },
];

const FLOW_STEPS = [
  { label: "Task", icon: FileText },
  { label: "Scope", icon: Waypoints },
  { label: "Questions", icon: SearchCheck },
  { label: "Evidence", icon: ShieldCheck },
  { label: "Report", icon: CheckCircle2 },
];

function ScopePreview({ requestSpec }: { requestSpec: RequestSpec }) {
  return (
    <div className="grid gap-3 md:grid-cols-2">
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">Parsed Subject</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">{requestSpec.subject}</CardContent>
      </Card>
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">Report Type</CardTitle>
        </CardHeader>
        <CardContent className="text-sm capitalize text-muted-foreground">
          {requestSpec.report_type.replaceAll("_", " ")}
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">Decision Context</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">{requestSpec.decision_context}</CardContent>
      </Card>
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">Scope Envelope</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          {requestSpec.geography} · {requestSpec.time_horizon} · {requestSpec.quality_target}
        </CardContent>
      </Card>
    </div>
  );
}

export default function NewReportPage() {
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [query, setQuery] = useState("");
  const [depth, setDepth] = useState<Depth>("standard");
  const [formats, setFormats] = useState<string[]>(["pdf", "html"]);
  const [perplexityHandoffEnabled, setPerplexityHandoffEnabled] = useState(false);
  const [pricing, setPricing] = useState<PricingTier[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [requestSpec, setRequestSpec] = useState<RequestSpec | null>(null);
  const [clarificationPack, setClarificationPack] = useState<ClarificationPack | null>(null);
  const [loadingCreate, setLoadingCreate] = useState(false);
  const [loadingQuestions, setLoadingQuestions] = useState(false);
  const [loadingScope, setLoadingScope] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reportSession = useReport(sessionId ?? "");
  const sse = useSSE(step >= 3 ? sessionId : null);

  useEffect(() => {
    getReportPricing()
      .then(setPricing)
      .catch((fetchError) => {
        console.error("Failed to load pricing", fetchError);
        setError("Failed to load pricing");
      });
  }, []);

  useEffect(() => {
    if (!sessionId) return;
    if (sse.isComplete) {
      void reportSession.refetch();
      setStep(4);
    }
    if (sse.isFailed) {
      void reportSession.refetch();
      setStep(3);
    }
  }, [reportSession.refetch, sessionId, sse.isComplete, sse.isFailed]);

  useEffect(() => {
    if (reportSession.status === "completed") {
      setStep(4);
    }
  }, [reportSession.status]);

  const selectedTier = useMemo(
    () => pricing.find((tier) => tier.depth === depth),
    [depth, pricing],
  );

  const toggleFormat = (format: string) => {
    setFormats((current) =>
      current.includes(format)
        ? current.filter((item) => item !== format)
        : [...current, format],
    );
  };

  const handleCreateRun = async () => {
    if (!query.trim()) return;
    setLoadingCreate(true);
      setError(null);
    try {
      const response = await createReport({
        request: query,
        depth,
        output_formats: formats,
        perplexity_handoff_enabled: perplexityHandoffEnabled,
      });
      setSessionId(response.session_id);
      setRequestSpec(response.request_spec);
      setStep(1);
    } catch (createError) {
      console.error(createError);
      setError(createError instanceof Error ? createError.message : "Failed to create a draft run");
    } finally {
      setLoadingCreate(false);
    }
  };

  const handleLoadQuestions = async () => {
    if (!sessionId) return;
    setLoadingQuestions(true);
    setError(null);
    try {
      const pack = await getClarificationPack(sessionId);
      setClarificationPack(pack);
      setStep(2);
    } catch (questionsError) {
      console.error(questionsError);
      setError(questionsError instanceof Error ? questionsError.message : "Failed to load clarification questions");
    } finally {
      setLoadingQuestions(false);
    }
  };

  const handleLockScope = async (answers: Record<string, string>) => {
    if (!sessionId) return;
    setLoadingScope(true);
    setError(null);
    try {
      const response = await scopeReport(sessionId, { answers });
      void reportSession.refetch();
      if (response.status === "awaiting_handoff") {
        router.push(`/app/reports/${sessionId}`);
        return;
      }
      setStep(3);
    } catch (scopeError) {
      console.error(scopeError);
      setError(scopeError instanceof Error ? scopeError.message : "Failed to lock scope");
    } finally {
      setLoadingScope(false);
    }
  };

  const auditSummary = reportSession.session?.audit_summary;
  const coverageReport = reportSession.session?.coverage_report;
  const analysisBrief = reportSession.session?.analysis_brief;

  return (
    <div className="mx-auto max-w-4xl space-y-8">
      <div className="flex flex-wrap items-center justify-center gap-2">
        {FLOW_STEPS.map((item, index) => (
          <div key={item.label} className="flex items-center gap-2">
            <div
              className={`flex items-center gap-2 rounded-full px-4 py-1.5 text-sm font-medium ${
                index === step
                  ? "bg-primary text-primary-foreground"
                  : index < step
                    ? "bg-primary/10 text-primary"
                    : "bg-muted text-muted-foreground"
              }`}
            >
              <item.icon className="h-3.5 w-3.5" />
              {item.label}
            </div>
            {index < FLOW_STEPS.length - 1 ? <div className="h-px w-8 bg-border" /> : null}
          </div>
        ))}
      </div>

      {error ? (
        <Card className="border-destructive/30 bg-destructive/5">
          <CardContent className="flex items-start gap-3 p-5 text-sm text-destructive">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <div>{error}</div>
          </CardContent>
        </Card>
      ) : null}

      {step === 0 ? (
        <div className="space-y-6">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Task</h1>
            <p className="mt-1 text-muted-foreground">
              Start from the decision, buyer, or rollout choice you need to support.
            </p>
          </div>

          <div className="space-y-3">
            <VoiceInput onTranscript={(text) => setQuery((prev) => (prev ? `${prev} ${text}` : text))} />
            <Textarea
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Evaluate LLM observability platforms for an enterprise document workflow product that must stay privacy-sensitive."
              className="min-h-[180px] resize-y text-[15px] leading-relaxed"
            />
          </div>

          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {DEPTHS.map((item) => (
              <button
                key={item.value}
                type="button"
                onClick={() => setDepth(item.value)}
                className={`rounded-lg border p-3 text-left ${
                  depth === item.value ? "border-primary bg-primary/5 ring-1 ring-primary" : "border-border"
                }`}
              >
                <div className="text-sm font-medium">{item.label}</div>
                <div className="mt-1 text-xs text-muted-foreground">{item.desc}</div>
              </button>
            ))}
          </div>

          {selectedTier ? (
            <Card className="border-primary/20 bg-primary/5">
              <CardContent className="flex flex-col gap-3 p-6 sm:flex-row sm:items-end sm:justify-between">
                <div>
                  <p className="text-2xl font-semibold tracking-tight">
                    {formatCost(selectedTier.public_price_usd)}
                  </p>
                  <p className="mt-1 text-sm text-muted-foreground">{selectedTier.description}</p>
                  <p className="mt-2 text-xs text-muted-foreground">
                    {selectedTier.initial_research_branches} primary branches, {selectedTier.adjacent_research_branches} side branches,{" "}
                    {selectedTier.validation_research_branches} validation branches, up to {selectedTier.quality_max_rounds} revision rounds
                  </p>
                </div>
                <div className="text-sm text-muted-foreground">
                  Runtime estimate: ~{selectedTier.estimated_time_minutes} min
                </div>
              </CardContent>
            </Card>
          ) : null}

          <div className="space-y-3">
            <label className="text-sm font-medium">Package formats</label>
            <div className="flex flex-wrap gap-4">
              {FORMATS.map((format) => (
                <label key={format.value} className="flex items-center gap-2 text-sm">
                  <Checkbox checked={formats.includes(format.value)} onCheckedChange={() => toggleFormat(format.value)} />
                  {format.label}
                </label>
              ))}
            </div>
          </div>

          <div className="space-y-3 rounded-2xl border border-dashed p-4">
            <label className="flex items-start gap-3 text-sm">
              <Checkbox
                checked={perplexityHandoffEnabled}
                onCheckedChange={(checked) => setPerplexityHandoffEnabled(Boolean(checked))}
              />
              <span className="space-y-1">
                <span className="block font-medium">Prepare Perplexity Deep Research handoff prompts</span>
                <span className="block text-muted-foreground">
                  The run will pause after scope lock, generate 3 ready-to-copy prompts, let you add your own materials, and only
                  then continue. This is the only version of the feature that actually helps save API money.
                </span>
              </span>
            </label>
          </div>

          <div className="flex justify-end">
            <Button onClick={handleCreateRun} disabled={!query.trim() || loadingCreate || formats.length === 0}>
              {loadingCreate ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Parsing task...
                </>
              ) : (
                <>
                  Create scope draft
                  <ArrowRight className="ml-2 h-4 w-4" />
                </>
              )}
            </Button>
          </div>
        </div>
      ) : null}

      {step === 1 && requestSpec ? (
        <div className="space-y-6">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Scope</h1>
            <p className="mt-1 text-muted-foreground">
              This is the structured interpretation of your task before research begins.
            </p>
          </div>

          <ScopePreview requestSpec={requestSpec} />

          {requestSpec.missing_critical_fields.length > 0 ? (
            <Card className="border-dashed">
              <CardHeader className="pb-3">
                <CardTitle className="text-sm">Missing critical fields</CardTitle>
              </CardHeader>
              <CardContent className="text-sm text-muted-foreground">
                {requestSpec.missing_critical_fields.join(", ")}
              </CardContent>
            </Card>
          ) : null}

          <div className="flex justify-between">
            <Button variant="ghost" onClick={() => setStep(0)}>
              Back
            </Button>
            <Button onClick={handleLoadQuestions} disabled={loadingQuestions}>
              {loadingQuestions ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Loading semantic questions...
                </>
              ) : (
                <>
                  Continue to questions
                  <ArrowRight className="ml-2 h-4 w-4" />
                </>
              )}
            </Button>
          </div>
        </div>
      ) : null}

      {step === 2 && clarificationPack ? (
        <div className="space-y-6">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Questions</h1>
            <p className="mt-1 text-muted-foreground">
              These answers become structured scope fields, not appended prompt text.
            </p>
          </div>

          <ClarifyingQuestions
            questions={clarificationPack.questions}
            onSubmit={handleLockScope}
            loading={loadingScope}
          />
        </div>
      ) : null}

      {step === 3 && sessionId ? (
        <div className="space-y-6">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Evidence</h1>
            <p className="mt-1 text-muted-foreground">
              The pipeline is building the research plan, source ledger, evidence ledger, report package, and audit.
            </p>
          </div>

          <Card>
            <CardContent className="p-6">
              <ReportProgress steps={sse.steps} currentStep={sse.currentStep} sessionId={sessionId} />
            </CardContent>
          </Card>

          {coverageReport ? (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Coverage Snapshot</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-sm text-muted-foreground">
                <p>
                  Coverage: {coverageReport.covered_questions}/{coverageReport.total_questions} primary questions
                </p>
                {coverageReport.questions.map((question) => (
                  <div key={question.question_id} className="rounded-lg border px-3 py-2">
                    <div className="font-medium text-foreground">{question.question}</div>
                    <div>
                      {question.evidence_count} evidence items · {question.source_count} source links · {question.status}
                    </div>
                  </div>
                ))}
              </CardContent>
            </Card>
          ) : null}

          {reportSession.status === "failed" || sse.isFailed ? (
            <Card className="border-destructive/30 bg-destructive/5">
              <CardContent className="space-y-3 p-5 text-sm text-destructive">
                <p>Generation failed or the release gate blocked publication.</p>
                {auditSummary?.failures?.length ? (
                  <ul className="list-disc pl-5">
                    {auditSummary.failures.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                ) : null}
                <div>
                  <Button variant="outline" asChild>
                    <Link href={`/app/reports/${sessionId}`}>Inspect run artifacts</Link>
                  </Button>
                </div>
              </CardContent>
            </Card>
          ) : null}
        </div>
      ) : null}

      {step === 4 && sessionId ? (
        <div className="space-y-6">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Report</h1>
            <p className="mt-1 text-muted-foreground">
              The report package is ready. Open the report workspace to inspect evidence, sources, and audit output.
            </p>
          </div>

          {analysisBrief ? (
            <Card className="border-primary/15 bg-primary/5">
              <CardHeader>
                <CardTitle>{analysisBrief.title}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4 text-sm text-muted-foreground">
                <p>{analysisBrief.executive_summary}</p>
                <div className="grid gap-4 md:grid-cols-2">
                  <div>
                    <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-foreground">
                      Recommendation posture
                    </p>
                    <p>{analysisBrief.recommendation_posture}</p>
                  </div>
                  <div>
                    <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-foreground">
                      Audit
                    </p>
                    <p>{auditSummary?.release_status ?? "pending"}</p>
                  </div>
                </div>
                <div>
                  <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-foreground">Key findings</p>
                  <ul className="list-disc pl-5">
                    {analysisBrief.key_findings.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </div>
              </CardContent>
            </Card>
          ) : null}

          <div className="flex flex-wrap gap-3">
            <Button asChild>
              <Link href={`/app/reports/${sessionId}`}>Open report workspace</Link>
            </Button>
            <Button variant="outline" onClick={() => router.push("/app")}>
              Back to dashboard
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
