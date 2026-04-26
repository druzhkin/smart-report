"use client";

/**
 * V4Shell — client wrapper that provides CostContext and renders the Masthead
 * with the current session cost.  Placed here so the parent layout.tsx can
 * remain a server component while the Masthead reacts to client-side state.
 */

import type { ReactNode } from "react";
import { CostProvider, useCost } from "@/lib/costContext";
import { Masthead } from "@/components/v4/Masthead";

function MastheadWithCost({ onReset }: { onReset?: () => void }) {
  const { cost } = useCost();
  return <Masthead cost={cost} onReset={onReset} />;
}

export function V4Shell({ children }: { children: ReactNode }) {
  return (
    <CostProvider>
      <MastheadWithCost />
      {children}
    </CostProvider>
  );
}
