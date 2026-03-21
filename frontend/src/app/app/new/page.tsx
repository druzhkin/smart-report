"use client";

import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  Mic,
  FileText,
  CheckCircle2,
  ArrowRight,
  ArrowLeft,
  Loader2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { VoiceInput } from "@/components/VoiceInput";
import { ClarifyingQuestions } from "@/components/ClarifyingQuestions";
import { ReportProgress } from "@/components/ReportProgress";
import { CostTracker } from "@/components/CostTracker";
import { createReport } from "@/lib/api";
import { useSSE } from "@/hooks/useSSE";
import { cn } from "@/lib/utils";

type Depth = "light" | "standard" | "deep" | "exhaustive";

const DEPTHS: { value: Depth; label: string; desc: string; time: string }[] = [
  { value: "light", label: "Light", desc: "Quick overview", time: "~2 min" },
  { value: "standard", label: "Standard", desc: "Balanced depth", time: "~5 min" },
  { value: "deep", label: "Deep", desc: "Thorough analysis", time: "~15 min" },
  { value: "exhaustive", label: "Exhaustive", desc: "Maximum depth", time: "~30 min" },
];

const FORMATS = [
  { value: "pdf", label: "PDF" },
  { value: "docx", label: "DOCX" },
  { value: "html", label: "HTML" },
  { value: "pptx", label: "Presentation" },
];

const STEPS = [
  { label: "Input", icon: FileText },
  { label: "Clarify", icon: Mic },
  { label: "Progress", icon: CheckCircle2 },
];

const MOCK_QUESTIONS = [
  "What is the target audience for this report?",
  "Which geographic regions should we focus on?",
  "What time period should the analysis cover?",
  "Are there specific competitors to include?",
  "What level of financial detail do you need?",
];

export default function NewReportPage() {
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [query, setQuery] = useState("");
  const [depth, setDepth] = useState<Depth>("standard");
  const [formats, setFormats] = useState<string[]>(["pdf", "docx"]);
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);

  const sse = useSSE(sessionId);

  const handleVoiceTranscript = useCallback((text: string) => {
    setQuery((prev) => (prev ? `${prev} ${text}` : text));
  }, []);

  const toggleFormat = (fmt: string) => {
    setFormats((prev) =>
      prev.includes(fmt) ? prev.filter((f) => f !== fmt) : [...prev, fmt]
    );
  };

  const handleStartPipeline = async (answers?: Record<string, string>) => {
    setLoading(true);
    try {
      const resp = await createReport({
        request: query,
        depth,
        output_formats: formats,
      });
      setSessionId(resp.session_id);
      setStep(2);
    } catch (err) {
      console.error("Failed:", err);
    } finally {
      setLoading(false);
    }
  };

  const goToReport = () => {
    if (sessionId) router.push(`/app/reports/${sessionId}`);
  };

  return (
    <div className="mx-auto max-w-2xl">
      {/* Step indicators */}
      <div className="mb-8 flex items-center justify-center gap-2">
        {STEPS.map((s, i) => (
          <div key={s.label} className="flex items-center gap-2">
            <motion.div
              className={cn(
                "flex items-center gap-2 rounded-full px-4 py-1.5 text-sm font-medium transition-colors",
                i === step
                  ? "bg-primary text-primary-foreground"
                  : i < step
                  ? "bg-primary/10 text-primary"
                  : "bg-muted text-muted-foreground"
              )}
              animate={{ scale: i === step ? 1 : 0.95 }}
            >
              <s.icon className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">{s.label}</span>
            </motion.div>
            {i < STEPS.length - 1 && (
              <div
                className={cn(
                  "h-px w-8",
                  i < step ? "bg-primary" : "bg-border"
                )}
              />
            )}
          </div>
        ))}
      </div>

      <AnimatePresence mode="wait">
        {/* STEP 1: Input */}
        {step === 0 && (
          <motion.div
            key="step-0"
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
            transition={{ duration: 0.25 }}
            className="space-y-6"
          >
            <div>
              <h1 className="text-2xl font-bold tracking-tight">
                What should we research?
              </h1>
              <p className="mt-1 text-muted-foreground">
                Describe your research topic in detail
              </p>
            </div>

            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <VoiceInput onTranscript={handleVoiceTranscript} />
              </div>

              <Textarea
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="e.g. Analyze the global AI chip market opportunity for 2025-2030, including competitive landscape, key players, and investment implications..."
                className="min-h-[180px] resize-y text-[15px] leading-relaxed"
              />
              <div className="flex justify-end">
                <span className="text-xs text-muted-foreground">
                  {query.length} characters
                </span>
              </div>
            </div>

            {/* Depth selector */}
            <div className="space-y-3">
              <label className="text-sm font-medium">Research Depth</label>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                {DEPTHS.map((d) => (
                  <button
                    key={d.value}
                    type="button"
                    onClick={() => setDepth(d.value)}
                    className={cn(
                      "flex flex-col rounded-lg border p-3 text-left transition-all",
                      depth === d.value
                        ? "border-primary bg-primary/5 ring-1 ring-primary"
                        : "border-border hover:border-primary/30"
                    )}
                  >
                    <span className="text-sm font-medium">{d.label}</span>
                    <span className="mt-0.5 text-xs text-muted-foreground">
                      {d.desc}
                    </span>
                    <span className="mt-1 font-mono text-xs text-primary">
                      {d.time}
                    </span>
                  </button>
                ))}
              </div>
            </div>

            {/* Output formats */}
            <div className="space-y-3">
              <label className="text-sm font-medium">Output Formats</label>
              <div className="flex flex-wrap gap-4">
                {FORMATS.map((f) => (
                  <label
                    key={f.value}
                    className="flex items-center gap-2 cursor-pointer"
                  >
                    <Checkbox
                      checked={formats.includes(f.value)}
                      onCheckedChange={() => toggleFormat(f.value)}
                    />
                    <span className="text-sm">{f.label}</span>
                  </label>
                ))}
              </div>
            </div>

            <div className="flex justify-end pt-2">
              <Button
                onClick={() => setStep(1)}
                disabled={!query.trim()}
                className="h-11 px-6"
              >
                Continue
                <ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            </div>
          </motion.div>
        )}

        {/* STEP 2: Clarifying Questions */}
        {step === 1 && (
          <motion.div
            key="step-1"
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
            transition={{ duration: 0.25 }}
            className="space-y-6"
          >
            <div>
              <h1 className="text-2xl font-bold tracking-tight">
                A few questions
              </h1>
              <p className="mt-1 text-muted-foreground">
                Help us tailor the report to your needs
              </p>
            </div>

            <Card className="bg-muted/30 border-dashed">
              <CardContent className="p-4">
                <p className="text-sm text-muted-foreground line-clamp-3">
                  {query}
                </p>
              </CardContent>
            </Card>

            <ClarifyingQuestions
              questions={MOCK_QUESTIONS}
              onSubmit={handleStartPipeline}
              loading={loading}
            />

            <div className="flex justify-start">
              <Button variant="ghost" onClick={() => setStep(0)}>
                <ArrowLeft className="mr-2 h-4 w-4" />
                Back
              </Button>
            </div>
          </motion.div>
        )}

        {/* STEP 3: Progress */}
        {step === 2 && (
          <motion.div
            key="step-2"
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
            transition={{ duration: 0.25 }}
            className="space-y-6"
          >
            <div className="flex items-center justify-between">
              <div>
                <h1 className="text-2xl font-bold tracking-tight">
                  {sse.isComplete
                    ? "Report Ready"
                    : sse.isFailed
                    ? "Pipeline Error"
                    : "Generating Report"}
                </h1>
                <p className="mt-1 text-muted-foreground">
                  {sse.isComplete
                    ? "Your report has been generated successfully"
                    : sse.isFailed
                    ? sse.error || "Something went wrong"
                    : "This may take a few minutes"}
                </p>
              </div>
              <CostTracker cost={sse.costUsd} />
            </div>

            <Card>
              <CardContent className="p-6">
                <ReportProgress
                  steps={sse.steps}
                  currentStep={sse.currentStep}
                  sessionId={sessionId}
                />
              </CardContent>
            </Card>

            {!sse.isComplete && !sse.isFailed && (
              <Card className="border-dashed bg-muted/20">
                <CardContent className="p-5 text-center">
                  <p className="text-sm text-muted-foreground">
                    You can leave this page. We&apos;ll notify you when the
                    report is ready.
                  </p>
                </CardContent>
              </Card>
            )}

            {sse.isComplete && (
              <motion.div
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ type: "spring", stiffness: 200, damping: 20 }}
              >
                <Button onClick={goToReport} className="w-full h-12 text-base">
                  View Report
                  <ArrowRight className="ml-2 h-4 w-4" />
                </Button>
              </motion.div>
            )}

            {sse.isFailed && (
              <Button
                variant="outline"
                onClick={() => {
                  setSessionId(null);
                  setStep(0);
                }}
              >
                Try Again
              </Button>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
