"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { MessageCircle, SkipForward, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface ClarifyingQuestionsProps {
  questions: string[];
  onSubmit: (answers: Record<string, string>) => void;
  loading?: boolean;
}

export function ClarifyingQuestions({
  questions,
  onSubmit,
  loading,
}: ClarifyingQuestionsProps) {
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [currentIdx, setCurrentIdx] = useState(0);

  if (questions.length === 0) return null;

  const isLast = currentIdx >= questions.length - 1;
  const allAnswered = questions.every(
    (_, i) => answers[String(i)]?.trim()
  );

  const handleNext = () => {
    if (isLast) return;
    setCurrentIdx((i) => i + 1);
  };

  const handleSkip = () => {
    if (isLast) {
      onSubmit(answers);
      return;
    }
    setCurrentIdx((i) => i + 1);
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <MessageCircle className="h-4 w-4 text-primary" />
          Clarifying Questions
        </CardTitle>
        <p className="text-sm text-muted-foreground">
          Answer these to improve report quality ({currentIdx + 1}/{questions.length})
        </p>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          <AnimatePresence mode="wait">
            <motion.div
              key={currentIdx}
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              transition={{ duration: 0.2 }}
            >
              <label className="text-sm font-medium">
                {questions[currentIdx]}
              </label>
              <Input
                value={answers[String(currentIdx)] || ""}
                onChange={(e) =>
                  setAnswers((prev) => ({
                    ...prev,
                    [String(currentIdx)]: e.target.value,
                  }))
                }
                placeholder="Your answer..."
                className="mt-2"
                autoFocus
              />
            </motion.div>
          </AnimatePresence>

          <div className="flex items-center justify-between pt-2">
            <Button variant="ghost" size="sm" onClick={handleSkip}>
              <SkipForward className="mr-1 h-4 w-4" />
              {isLast ? "Skip & Generate" : "Skip"}
            </Button>

            <div className="flex gap-2">
              {!isLast ? (
                <Button
                  size="sm"
                  onClick={handleNext}
                  disabled={!answers[String(currentIdx)]?.trim()}
                >
                  Next
                  <ArrowRight className="ml-1 h-4 w-4" />
                </Button>
              ) : (
                <Button
                  size="sm"
                  onClick={() => onSubmit(answers)}
                  disabled={loading}
                >
                  {loading ? "Starting..." : "Generate Report"}
                  <ArrowRight className="ml-1 h-4 w-4" />
                </Button>
              )}
            </div>
          </div>

          <div className="flex gap-1.5 justify-center pt-1">
            {questions.map((_, i) => (
              <motion.div
                key={i}
                className={`h-1.5 rounded-full transition-colors ${
                  i === currentIdx
                    ? "w-6 bg-primary"
                    : i < currentIdx
                    ? "w-1.5 bg-primary/40"
                    : "w-1.5 bg-muted"
                }`}
                layout
              />
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
