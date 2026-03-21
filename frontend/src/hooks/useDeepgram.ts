"use client";

import { useCallback, useRef, useState } from "react";

interface DeepgramOptions {
  language?: string;
  silenceTimeout?: number;
}

interface DeepgramState {
  transcript: string;
  interimTranscript: string;
  isRecording: boolean;
  isConnecting: boolean;
  isAvailable: boolean;
  error: string | null;
  start: () => Promise<void>;
  stop: () => void;
  reset: () => void;
}

export function useDeepgram(options: DeepgramOptions = {}): DeepgramState {
  const { language = "en", silenceTimeout = 3000 } = options;

  const [transcript, setTranscript] = useState("");
  const [interimTranscript, setInterimTranscript] = useState("");
  const [isRecording, setIsRecording] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);
  const [isAvailable, setIsAvailable] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const mediaRef = useRef<MediaRecorder | null>(null);
  const silenceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const resetSilenceTimer = useCallback(() => {
    if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current);
    silenceTimerRef.current = setTimeout(() => {
      stop();
    }, silenceTimeout);
  }, [silenceTimeout]);

  const stop = useCallback(() => {
    if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current);
    mediaRef.current?.stop();
    mediaRef.current?.stream.getTracks().forEach((t) => t.stop());
    wsRef.current?.close();
    mediaRef.current = null;
    wsRef.current = null;
    setIsRecording(false);
    setIsConnecting(false);
    setInterimTranscript("");
  }, []);

  const start = useCallback(async () => {
    setError(null);
    setIsConnecting(true);

    try {
      const tokenResponse = await fetch("/api/settings/deepgram/token", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });

      if (!tokenResponse.ok) {
        setIsAvailable(false);
        const payload = (await tokenResponse.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(payload?.detail || "Voice input is unavailable");
      }

      const tokenPayload = (await tokenResponse.json()) as { access_token: string };
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const ws = new WebSocket(
        `wss://api.deepgram.com/v1/listen?token=${encodeURIComponent(tokenPayload.access_token)}&language=${language}&model=nova-3&smart_format=true&interim_results=true&vad_events=true`
      );
      wsRef.current = ws;

      ws.onopen = () => {
        const recorder = new MediaRecorder(stream, { mimeType: "audio/webm" });
        mediaRef.current = recorder;

        recorder.ondataavailable = (e) => {
          if (ws.readyState === WebSocket.OPEN && e.data.size > 0) {
            ws.send(e.data);
          }
        };

        recorder.start(250);
        setIsRecording(true);
        setIsConnecting(false);
        resetSilenceTimer();
      };

      ws.onmessage = (e) => {
        const data = JSON.parse(e.data);
        const alt = data?.channel?.alternatives?.[0];
        if (!alt) return;

        const text = alt.transcript;
        if (!text) return;

        resetSilenceTimer();

        if (data.is_final) {
          setTranscript((prev) => (prev ? `${prev} ${text}` : text));
          setInterimTranscript("");
        } else {
          setInterimTranscript(text);
        }
      };

      ws.onerror = () => {
        setError("Voice transcription connection failed");
        stop();
      };

      ws.onclose = () => {
        setIsRecording(false);
        setIsConnecting(false);
      };
    } catch (err) {
      setError(err instanceof Error ? err.message : "Microphone access denied");
      setIsConnecting(false);
    }
  }, [language, resetSilenceTimer, stop]);

  const reset = useCallback(() => {
    stop();
    setTranscript("");
    setInterimTranscript("");
    setError(null);
  }, [stop]);

  return {
    transcript,
    interimTranscript,
    isRecording,
    isConnecting,
    isAvailable,
    error,
    start,
    stop,
    reset,
  };
}
