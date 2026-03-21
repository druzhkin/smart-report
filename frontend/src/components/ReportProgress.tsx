"use client";

import { motion } from "framer-motion";
import { Check, Loader2 } from "lucide-react";
import { useState } from "react";
import { usePushNotifications } from "@/hooks/usePushNotifications";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { formatDuration } from "@/lib/utils";
import type { PipelineStep } from "@/hooks/useSSE";

interface ReportProgressProps {
  steps: PipelineStep[];
  currentStep: string | null;
  sessionId: string | null;
}

export function ReportProgress({ steps, currentStep, sessionId }: ReportProgressProps) {
  const completedCount = steps.filter((s) => s.status === "done").length;
  const progress = (completedCount / steps.length) * 100;
  const [subscribeError, setSubscribeError] = useState<string | null>(null);
  const { isSupported, isSubscribed, subscribe } = usePushNotifications(sessionId);

  const handleSubscribe = async () => {
    try {
      setSubscribeError(null);
      await subscribe();
    } catch (error) {
      setSubscribeError(
        error instanceof Error ? error.message : "Не удалось включить уведомления"
      );
    }
  };

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <div className="flex items-center justify-between text-sm">
          <span className="text-muted-foreground">Pipeline Progress</span>
          <span className="font-mono text-muted-foreground">
            {completedCount}/{steps.length}
          </span>
        </div>
        <div className="h-2 w-full overflow-hidden rounded-full bg-secondary">
          <motion.div
            className="h-full bg-primary"
            initial={{ width: 0 }}
            animate={{ width: `${progress}%` }}
            transition={{ duration: 0.5, ease: "easeOut" }}
          />
        </div>
      </div>

      <div className="space-y-1">
        {steps.map((step, i) => {
          const elapsed =
            step.startedAt && step.status === "active"
              ? Date.now() - step.startedAt
              : step.startedAt && step.completedAt
              ? step.completedAt - step.startedAt
              : null;

          return (
            <motion.div
              key={step.key}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.05 }}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2.5 transition-colors",
                step.status === "active" && "bg-primary/5"
              )}
            >
              <div className="flex h-7 w-7 shrink-0 items-center justify-center">
                {step.status === "done" ? (
                  <motion.div
                    initial={{ scale: 0.5 }}
                    animate={{ scale: 1 }}
                    transition={{ type: "spring", stiffness: 300, damping: 20 }}
                    className="flex h-6 w-6 items-center justify-center rounded-full bg-emerald-100 text-emerald-600"
                  >
                    <Check className="h-3.5 w-3.5" />
                  </motion.div>
                ) : step.status === "active" ? (
                  <div className="flex h-6 w-6 items-center justify-center rounded-full bg-primary/10 text-primary">
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  </div>
                ) : step.status === "error" ? (
                  <div className="h-2.5 w-2.5 rounded-full bg-destructive" />
                ) : (
                  <div className="h-2.5 w-2.5 rounded-full bg-muted-foreground/30" />
                )}
              </div>

              <div className="flex flex-1 items-center justify-between min-w-0">
                <div className="min-w-0">
                  <p
                    className={cn(
                      "text-sm",
                      step.status === "active"
                        ? "font-medium text-foreground"
                        : step.status === "done"
                        ? "text-foreground"
                        : "text-muted-foreground"
                    )}
                  >
                    {step.label}
                  </p>
                  {step.message && step.status === "active" && (
                    <p className="text-xs text-muted-foreground truncate">
                      {step.message}
                    </p>
                  )}
                </div>

                {elapsed !== null && (
                  <span className="ml-2 shrink-0 font-mono text-xs text-muted-foreground">
                    {formatDuration(elapsed)}
                  </span>
                )}
              </div>
            </motion.div>
          );
        })}
      </div>

      {sessionId && currentStep && !isSubscribed && isSupported && (
        <div className="rounded-lg border border-dashed bg-muted/20 p-4">
          <Button type="button" variant="outline" onClick={handleSubscribe}>
            {"\uD83D\uDD14"} Уведомить когда готово
          </Button>
          {subscribeError && (
            <p className="mt-2 text-sm text-destructive">{subscribeError}</p>
          )}
        </div>
      )}

      {isSubscribed && (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
          ✓ Уведомим вас
        </div>
      )}
    </div>
  );
}
