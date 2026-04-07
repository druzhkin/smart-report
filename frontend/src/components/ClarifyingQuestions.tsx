"use client";

import { useState } from "react";
import { ArrowRight, MessageCircle, SkipForward } from "lucide-react";

import type { ClarificationQuestion } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

interface ClarifyingQuestionsProps {
  questions: ClarificationQuestion[];
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

  const current = questions[currentIdx];
  const isLast = currentIdx >= questions.length - 1;
  const currentAnswer = answers[current.question_id] ?? "";

  const handleNext = () => {
    if (!isLast) setCurrentIdx((value) => value + 1);
  };

  const handleSkip = () => {
    if (isLast) {
      onSubmit(answers);
      return;
    }
    setCurrentIdx((value) => value + 1);
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <MessageCircle className="h-4 w-4 text-primary" />
          Semantic Questions
        </CardTitle>
        <p className="text-sm text-muted-foreground">
          {currentIdx + 1}/{questions.length} questions. Answers become structured scope, not appended prompt text.
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <label className="text-sm font-medium">{current.prompt}</label>
          <p className="text-xs text-muted-foreground">{current.rationale}</p>
          <Input
            value={currentAnswer}
            onChange={(event) =>
              setAnswers((prev) => ({
                ...prev,
                [current.question_id]: event.target.value,
              }))
            }
            placeholder={current.placeholder || "Your answer"}
            autoFocus
          />
        </div>

        <div className="flex items-center justify-between pt-2">
          <Button variant="ghost" size="sm" onClick={handleSkip}>
            <SkipForward className="mr-1 h-4 w-4" />
            {isLast ? "Skip & Start" : "Skip"}
          </Button>

          {!isLast ? (
            <Button size="sm" onClick={handleNext} disabled={current.required && !currentAnswer.trim()}>
              Next
              <ArrowRight className="ml-1 h-4 w-4" />
            </Button>
          ) : (
            <Button size="sm" onClick={() => onSubmit(answers)} disabled={loading}>
              {loading ? "Starting..." : "Lock Scope"}
              <ArrowRight className="ml-1 h-4 w-4" />
            </Button>
          )}
        </div>

        <div className="flex gap-1.5 justify-center pt-1">
          {questions.map((question, index) => (
            <div
              key={question.question_id}
              className={`h-1.5 rounded-full transition-colors ${
                index === currentIdx
                  ? "w-6 bg-primary"
                  : index < currentIdx
                  ? "w-2 bg-primary/40"
                  : "w-2 bg-muted"
              }`}
            />
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
