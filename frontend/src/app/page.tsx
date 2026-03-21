"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { ArrowRight, FileText, Brain, Zap } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { getReportPricing, type PricingTier } from "@/lib/api";
import { formatCost } from "@/lib/utils";

const steps = [
  {
    icon: FileText,
    title: "Describe",
    description: "Tell us what you need — type or dictate your research question",
  },
  {
    icon: Brain,
    title: "AI Research",
    description: "8 specialized agents research, verify, and synthesize findings",
  },
  {
    icon: Zap,
    title: "Receive",
    description: "Get a polished report with citations, charts, and presentation",
  },
];

export default function LandingPage() {
  const [pricing, setPricing] = useState<PricingTier[]>([]);

  useEffect(() => {
    getReportPricing()
      .then(setPricing)
      .catch((error) => console.error("Failed to load pricing", error));
  }, []);

  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex items-center justify-between px-6 py-4 lg:px-12">
        <Link href="/" className="text-lg font-semibold tracking-tight">
          Smart Report
        </Link>
        <Link href="/app/new">
          <Button variant="ghost" size="sm">
            Sign in
          </Button>
        </Link>
      </header>

      <main className="flex flex-1 flex-col items-center justify-center px-6 py-24">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="max-w-2xl text-center"
        >
          <h1 className="text-4xl font-bold tracking-tight sm:text-5xl lg:text-6xl">
            Research reports,{" "}
            <motion.span
              className="text-primary"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.3, duration: 0.5 }}
            >
              automated
            </motion.span>
          </h1>
          <p className="mt-6 text-lg text-muted-foreground leading-relaxed">
            Describe your research question. Our AI pipeline delivers
            McKinsey-grade analysis with verified sources in minutes.
          </p>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.5 }}
            className="mt-10"
          >
            <Link href="/app/new">
              <Button size="lg" className="h-12 px-8 text-base">
                Start for free
                <ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            </Link>
          </motion.div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 40 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.6, duration: 0.5 }}
          className="mt-32 grid w-full max-w-4xl gap-8 sm:grid-cols-3"
        >
          {steps.map((step, i) => (
            <motion.div
              key={step.title}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.7 + i * 0.15 }}
              className="text-center"
            >
              <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-primary/10 text-primary">
                <step.icon className="h-5 w-5" />
              </div>
              <h3 className="mt-4 text-sm font-semibold">{step.title}</h3>
              <p className="mt-2 text-sm text-muted-foreground leading-relaxed">
                {step.description}
              </p>
            </motion.div>
          ))}
        </motion.div>

        {pricing.length > 0 && (
          <motion.section
            initial={{ opacity: 0, y: 40 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.85, duration: 0.5 }}
            className="mt-24 w-full max-w-5xl"
          >
            <div className="text-center">
              <h2 className="text-2xl font-bold tracking-tight">Transparent pricing</h2>
              <p className="mt-3 text-sm text-muted-foreground">
                Fixed price by research depth, visible before launch.
              </p>
            </div>

            <div className="mt-8 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              {pricing.map((tier) => (
                <div
                  key={tier.depth}
                  className="rounded-2xl border border-border/70 bg-background p-5 text-left shadow-sm"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-sm font-semibold">{tier.label}</p>
                      <p className="mt-1 text-xs uppercase tracking-[0.18em] text-muted-foreground">
                        {tier.tagline}
                      </p>
                    </div>
                    <span className="rounded-full bg-primary/10 px-2.5 py-1 text-xs font-medium text-primary">
                      ~{tier.estimated_time_minutes} min
                    </span>
                  </div>

                  <p className="mt-5 text-3xl font-bold tracking-tight">
                    {formatCost(tier.public_price_usd)}
                  </p>
                  <p className="mt-2 text-sm leading-6 text-muted-foreground">
                    {tier.description}
                  </p>
                </div>
              ))}
            </div>
          </motion.section>
        )}
      </main>

      <footer className="py-8 text-center text-xs text-muted-foreground">
        Smart Report System
      </footer>
    </div>
  );
}
