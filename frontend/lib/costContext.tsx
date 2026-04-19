"use client";

/**
 * CostContext — lets session pages broadcast their current total_cost_rub up
 * to the Masthead without prop-drilling through the Next.js server layout.
 *
 * Usage in a page:
 *   const { setCost } = useCost();
 *   // after getSession():
 *   setCost(session.total_cost_rub);
 *
 * The Masthead reads cost via useCost() and renders it when cost > 0.
 */

import { createContext, useContext, useState, type ReactNode } from "react";

type CostCtx = {
  cost: number | null;
  setCost: (rub: number) => void;
};

const CostContext = createContext<CostCtx>({
  cost: null,
  setCost: () => {},
});

export function CostProvider({ children }: { children: ReactNode }) {
  const [cost, setCostRaw] = useState<number | null>(null);

  function setCost(rub: number) {
    // Only show badge when cost > 0; round to integer rubles.
    setCostRaw(rub > 0 ? Math.round(rub) : null);
  }

  return (
    <CostContext.Provider value={{ cost, setCost }}>
      {children}
    </CostContext.Provider>
  );
}

export function useCost(): CostCtx {
  return useContext(CostContext);
}
