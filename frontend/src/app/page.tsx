"use client";

import { motion } from "framer-motion";
import { ArrowRight, FileText, Brain, Zap } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";

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
      </main>

      <footer className="py-8 text-center text-xs text-muted-foreground">
        Smart Report System
      </footer>
    </div>
  );
}
