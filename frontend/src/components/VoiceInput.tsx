"use client";

import { motion, AnimatePresence } from "framer-motion";
import { Mic, MicOff, Loader2 } from "lucide-react";
import { useDeepgram } from "@/hooks/useDeepgram";
import { Button } from "@/components/ui/button";

interface VoiceInputProps {
  onTranscript: (text: string) => void;
}

export function VoiceInput({ onTranscript }: VoiceInputProps) {
  const {
    transcript,
    interimTranscript,
    isRecording,
    isConnecting,
    isAvailable,
    error,
    start,
    stop,
  } = useDeepgram();

  const fullText = [transcript, interimTranscript].filter(Boolean).join(" ");

  if (fullText && !isRecording) {
    onTranscript(fullText);
  }

  return (
    <div className="flex items-center gap-3">
      <Button
        type="button"
        variant={isRecording ? "destructive" : "secondary"}
        size="icon"
        onClick={isRecording ? stop : start}
        disabled={isConnecting || !isAvailable}
        className="relative shrink-0 rounded-full h-12 w-12"
      >
        <AnimatePresence mode="wait">
          {isConnecting ? (
            <motion.div
              key="connecting"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
            >
              <Loader2 className="h-5 w-5 animate-spin" />
            </motion.div>
          ) : isRecording ? (
            <motion.div
              key="recording"
              initial={{ scale: 0.8 }}
              animate={{ scale: 1 }}
              exit={{ scale: 0.8 }}
            >
              <MicOff className="h-5 w-5" />
            </motion.div>
          ) : (
            <motion.div
              key="idle"
              initial={{ scale: 0.8 }}
              animate={{ scale: 1 }}
              exit={{ scale: 0.8 }}
            >
              <Mic className="h-5 w-5" />
            </motion.div>
          )}
        </AnimatePresence>

        {isRecording && (
          <motion.span
            className="absolute inset-0 rounded-full border-2 border-destructive"
            initial={{ scale: 1, opacity: 0.6 }}
            animate={{ scale: 1.4, opacity: 0 }}
            transition={{ duration: 1.2, repeat: Infinity }}
          />
        )}
      </Button>

      <span className="text-sm text-muted-foreground">
        {isConnecting
          ? "Connecting..."
          : isRecording
          ? "Listening... speak now"
          : !isAvailable
          ? "Voice input is not configured"
          : error
          ? error
          : "Click to dictate"}
      </span>
    </div>
  );
}
