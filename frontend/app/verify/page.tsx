"use client";

import { useState, useRef, FormEvent, ChangeEvent, KeyboardEvent, useEffect, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";

export const dynamic = "force-dynamic";

function VerifyPageInner() {
  const router = useRouter();
  const params = useSearchParams();
  const email = params.get("email") || "";
  const next = params.get("next") || "/new";

  const [digits, setDigits] = useState<string[]>(Array(6).fill(""));
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputs = useRef<(HTMLInputElement | null)[]>([]);

  useEffect(() => {
    inputs.current[0]?.focus();
  }, []);

  function setDigit(i: number, v: string) {
    const clean = v.replace(/\D/g, "").slice(0, 1);
    setDigits((prev) => {
      const n = [...prev];
      n[i] = clean;
      return n;
    });
    if (clean && i < 5) inputs.current[i + 1]?.focus();
  }

  function onPaste(e: React.ClipboardEvent<HTMLInputElement>) {
    const pasted = e.clipboardData.getData("text").replace(/\D/g, "").slice(0, 6);
    if (!pasted) return;
    e.preventDefault();
    const arr = pasted.split("").concat(Array(6).fill("")).slice(0, 6);
    setDigits(arr);
    inputs.current[Math.min(pasted.length, 5)]?.focus();
  }

  function onKey(e: KeyboardEvent<HTMLInputElement>, i: number) {
    if (e.key === "Backspace" && !digits[i] && i > 0) {
      inputs.current[i - 1]?.focus();
    }
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const code = digits.join("");
    if (code.length < 6 || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch("/api/auth/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, code }),
      });
      if (!res.ok && res.status !== 404) {
        setError("Код неверный или истёк. Попробуйте ещё раз.");
        setSubmitting(false);
        return;
      }
      router.push(next);
    } catch {
      router.push(next);
    }
  }

  const full = digits.every((d) => d);

  return (
    <div className="min-h-screen w-full flex flex-col bg-[#FAFAFA] text-slate-500 relative overflow-hidden">
      <div className="fixed inset-0 overflow-hidden pointer-events-none z-0 mix-blend-multiply opacity-70">
        <div className="absolute top-[-10%] left-[-10%] w-[600px] h-[600px] rounded-full bg-slate-200/50 blur-[100px]" />
        <div className="absolute bottom-[-20%] right-[-10%] w-[500px] h-[500px] rounded-full bg-blue-100/40 blur-[100px]" />
      </div>

      <header className="relative z-10 px-6 lg:px-8 h-14 flex items-center">
        <Link href="/" className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-md bg-slate-900 flex items-center justify-center shadow-sm">
            <span className="text-white text-[10px] font-semibold">SR</span>
          </div>
          <span className="font-semibold tracking-tight text-slate-900">Smart Report</span>
        </Link>
      </header>

      <main className="flex-1 flex items-center justify-center px-6 relative z-10">
        <div className="w-full max-w-md">
          <div className="bg-white/80 backdrop-blur-xl border border-slate-200 rounded-2xl p-8 shadow-sm">
            <h1 className="text-2xl font-semibold tracking-tight text-slate-900">Подтверждение</h1>
            <p className="mt-2 text-sm text-slate-500">
              Отправили 6-значный код на{" "}
              <span className="font-medium text-slate-700">{email || "ваш email"}</span>. Код действует 10 минут.
            </p>

            <form onSubmit={onSubmit} className="mt-6 space-y-5">
              <div className="flex gap-2 justify-between">
                {digits.map((d, i) => (
                  <input
                    key={i}
                    ref={(el) => {
                      inputs.current[i] = el;
                    }}
                    type="text"
                    inputMode="numeric"
                    maxLength={1}
                    value={d}
                    onChange={(e: ChangeEvent<HTMLInputElement>) => setDigit(i, e.target.value)}
                    onKeyDown={(e) => onKey(e, i)}
                    onPaste={onPaste}
                    className="w-11 h-14 text-center text-xl font-mono font-semibold text-slate-900 bg-white border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-slate-900/10 focus:border-slate-900"
                  />
                ))}
              </div>

              {error && <p className="text-sm text-red-600">{error}</p>}

              <button
                type="submit"
                disabled={!full || submitting}
                className="w-full px-4 py-2.5 text-sm font-medium text-white bg-slate-900 rounded-lg hover:bg-slate-800 transition-all shadow-sm active:scale-[0.98] disabled:opacity-60 disabled:cursor-not-allowed"
              >
                {submitting ? "Проверяем…" : "Войти"}
              </button>
            </form>

            <p className="mt-5 text-center text-xs text-slate-400">
              Не пришёл код?{" "}
              <Link href={`/login?email=${encodeURIComponent(email)}&next=${encodeURIComponent(next)}`} className="underline hover:text-slate-600">
                Отправить ещё раз
              </Link>
            </p>
          </div>
        </div>
      </main>
    </div>
  );
}

export default function VerifyPage() {
  return (
    <Suspense fallback={null}>
      <VerifyPageInner />
    </Suspense>
  );
}
