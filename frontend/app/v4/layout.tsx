"use client";

import { useEffect, useState, type ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";
import { V4Shell } from "./V4Shell";

// Routes under /v4/* that ship their own full-viewport chrome and must
// NOT be wrapped in the legacy V4Shell (which would double up mastheads
// and break layout). The new chat workspace at /v4/chat owns its own
// top bar, theme, sidebar, and cost badge.
const OWN_CHROME = ["/v4/chat"];
const STUB = process.env.NEXT_PUBLIC_V4_STUB === "1";

/**
 * SaaS auth gate. /v4/* is the user workspace — every route here requires
 * the session cookie set by /api/auth/login. On mount we hit /api/auth/me;
 * if not authenticated we replace() to /login?next=<current> so the user
 * lands back here after signing in.
 *
 * Avoids gating the full app (landing/signup/login stay public). State is
 * kept in `phase` so we don't render workspace UI to unauthorized eyes
 * even for the brief moment before the redirect kicks in.
 */
function useAuthGate() {
  const router = useRouter();
  const pathname = usePathname() || "";
  const [phase, setPhase] = useState<"checking" | "ok">("checking");

  useEffect(() => {
    if (STUB) {
      setPhase("ok");
      return;
    }
    let cancelled = false;
    fetch("/api/auth/me", { cache: "no-store" })
      .then((r) => r.json())
      .then((d) => {
        if (cancelled) return;
        if (d?.authenticated) {
          setPhase("ok");
        } else {
          const next = encodeURIComponent(pathname || "/v4/chat");
          router.replace(`/login?next=${next}`);
        }
      })
      .catch(() => {
        if (cancelled) return;
        const next = encodeURIComponent(pathname || "/v4/chat");
        router.replace(`/login?next=${next}`);
      });
    return () => { cancelled = true; };
  }, [pathname, router]);

  return phase;
}

function AuthGateLoader() {
  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        color: "#9F9F9F",
        fontFamily: "'JetBrains Mono', ui-monospace, monospace",
        fontSize: 12,
        letterSpacing: "0.06em",
      }}
    >
      проверяем сессию…
    </div>
  );
}

export default function V4Layout({ children }: { children: ReactNode }) {
  const pathname = usePathname() || "";
  const skipShell = OWN_CHROME.some((r) => pathname === r || pathname.startsWith(r + "/"));
  const phase = useAuthGate();

  if (phase !== "ok") {
    return <AuthGateLoader />;
  }

  if (skipShell) {
    return <>{children}</>;
  }

  return (
    <div className="v4" data-theme="v4">
      <V4Shell>
        <main>{children}</main>
      </V4Shell>
    </div>
  );
}
