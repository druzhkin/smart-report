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
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const ws = new WebSocket(
        `wss://api.deepgram.com/v1/listen?language=${language}&model=nova-3&smart_format=true&interim_results=true&vad_events=true`
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
        setError("Connection error");
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
    error,
    start,
    stop,
    reset,
  };
}
