"use client";

import { motion } from "framer-motion";
import { DollarSign } from "lucide-react";
import { cn } from "@/lib/utils";

interface CostTrackerProps {
  cost: number;
  maxBudget?: number;
}

export function CostTracker({ cost, maxBudget = 2.0 }: CostTrackerProps) {
  const percentage = Math.min((cost / maxBudget) * 100, 100);
  const isWarning = percentage > 70;
  const isDanger = percentage > 90;

  return (
    <div className="flex items-center gap-3">
      <DollarSign className="h-4 w-4 text-muted-foreground" />
      <div className="w-20 h-1.5 overflow-hidden rounded-full bg-secondary">
        <motion.div
          className={cn(
            "h-full rounded-full",
            isDanger ? "bg-destructive" : isWarning ? "bg-amber-500" : "bg-primary"
          )}
          initial={{ width: 0 }}
          animate={{ width: `${percentage}%` }}
          transition={{ duration: 0.5, ease: "easeOut" }}
        />
      </div>
      <span
        className={cn(
          "font-mono text-sm",
          isDanger ? "text-destructive" : "text-muted-foreground"
        )}
      >
        ${cost.toFixed(2)} / ${maxBudget.toFixed(2)}
      </span>
    </div>
  );
}
