"use client";

import { useState, FormEvent, Suspense, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";

export const dynamic = "force-dynamic";

// Coerce Pydantic 422 response (`detail` may be array of error objects) into
// a readable single string so React doesn't crash trying to render objects.
function formatError(data: any, fallback: string): string {
  if (!data) return fallback;
  const d = data.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) {
    return d
      .map((e: any) => {
        const where = Array.isArray(e?.loc) ? e.loc.join(".") : "";
        const msg = e?.msg || e?.type || JSON.stringify(e);
        return where ? `${where}: ${msg}` : msg;
      })
      .join("; ");
  }
  if (d && typeof d === "object") return JSON.stringify(d);
  return fallback;
}

function LoginPageInner() {
  const router = useRouter();
  const params = useSearchParams();
  const next = params.get("next") || "/v4/chat";
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  // If already authenticated, bounce straight to next.
  useEffect(() => {
    fetch("/api/auth/me")
      .then((r) => r.json())
      .then((d) => {
        if (d?.authenticated) router.replace(next);
      })
      .catch(() => {});
  }, [next, router]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!email || !password || submitting) return;
    setSubmitting(true);
    setError("");
    try {
      const endpoint = mode === "signup" ? "/api/auth/signup" : "/api/auth/login";
      const res = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      if (res.ok) {
        router.replace(next);
        return;
      }
      const data = await res.json().catch(() => ({}));
      setError(formatError(data, `HTTP ${res.status}`));
    } catch (err: any) {
      setError(String(err?.message || err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen w-full flex flex-col bg-[#FAFAFA] text-slate-500 relative overflow-hidden">
      <div className="fixed inset-0 overflow-hidden pointer-events-none z-0 mix-blend-multiply opacity-70">
        <div className="absolute top-[-10%] left-[-10%] w-[600px] h-[600px] rounded-full bg-slate-200/50 blur-[100px]" />
        <div className="absolute bottom-[-20%] right-[-10%] w-[500px] h-[500px] rounded-full bg-blue-100/40 blur-[100px]" />
      </div>

      <header className="relative z-10 px-6 lg:px-8 h-14 flex items-center">
        <Link href="/" className="flex items-center gap-2 group">
          <div className="w-6 h-6 rounded-md bg-slate-900 flex items-center justify-center shadow-sm">
            <span className="text-white text-[10px] font-semibold">SR</span>
          </div>
          <span className="font-semibold tracking-tight text-slate-900">Smart Report</span>
        </Link>
      </header>

      <main className="flex-1 flex items-center justify-center px-6 relative z-10">
        <div className="w-full max-w-md">
          <div className="bg-white/80 backdrop-blur-xl border border-slate-200 rounded-2xl p-8 shadow-sm">
            <h1 className="text-2xl font-semibold tracking-tight text-slate-900">
              {mode === "signup" ? "Регистрация" : "Вход"}
            </h1>
            <p className="mt-2 text-sm text-slate-500">
              {mode === "signup"
                ? "Email и пароль (минимум 6 символов). Бесплатный доступ к demo-режиму, без подтверждения email."
                : "Email и пароль, которые использовали при регистрации."}
            </p>

            <form onSubmit={onSubmit} className="mt-6 space-y-4">
              {error && (
                <div className="rounded-lg bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
                  {error}
                </div>
              )}
              <label className="block">
                <span className="text-xs font-medium text-slate-600 uppercase tracking-wide">Email</span>
                <input
                  type="email"
                  required
                  autoFocus
                  autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@company.com"
                  className="mt-1.5 w-full px-3 py-2.5 rounded-lg border border-slate-200 bg-white text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-slate-900/10 focus:border-slate-900"
                />
              </label>
              <label className="block">
                <span className="text-xs font-medium text-slate-600 uppercase tracking-wide">Пароль</span>
                <input
                  type="password"
                  required
                  minLength={6}
                  autoComplete={mode === "signup" ? "new-password" : "current-password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="mt-1.5 w-full px-3 py-2.5 rounded-lg border border-slate-200 bg-white text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-slate-900/10 focus:border-slate-900"
                />
              </label>
              <button
                type="submit"
                disabled={!email || !password || submitting}
                className="w-full px-4 py-2.5 text-sm font-medium text-white bg-slate-900 rounded-lg hover:bg-slate-800 transition-all shadow-sm active:scale-[0.98] disabled:opacity-60 disabled:cursor-not-allowed"
              >
                {submitting
                  ? mode === "signup"
                    ? "Создаём…"
                    : "Входим…"
                  : mode === "signup"
                  ? "Зарегистрироваться"
                  : "Войти"}
              </button>
            </form>

            <div className="mt-5 flex items-center gap-3 text-xs text-slate-400">
              <div className="flex-1 h-px bg-slate-200" />
              <span>{mode === "signup" ? "Уже есть аккаунт?" : "Нет аккаунта?"}</span>
              <div className="flex-1 h-px bg-slate-200" />
            </div>

            <button
              type="button"
              onClick={() => {
                setError("");
                setMode(mode === "signup" ? "login" : "signup");
              }}
              className="mt-5 w-full px-4 py-2.5 text-sm font-medium text-slate-700 bg-white border border-slate-200 rounded-lg hover:bg-slate-50 transition-all shadow-sm active:scale-[0.98]"
            >
              {mode === "signup" ? "Войти" : "Зарегистрироваться"}
            </button>
          </div>

          <p className="mt-6 text-center text-xs text-slate-400">
            Нажимая «Войти» / «Зарегистрироваться», вы соглашаетесь с{" "}
            <a href="/terms" className="underline hover:text-slate-600">условиями</a>{" "}и{" "}
            <a href="/privacy" className="underline hover:text-slate-600">политикой конфиденциальности</a>.
          </p>
        </div>
      </main>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginPageInner />
    </Suspense>
  );
}
