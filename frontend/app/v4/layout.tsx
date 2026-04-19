"use client";

import type { ReactNode } from "react";
import { usePathname } from "next/navigation";
import { V4Shell } from "./V4Shell";

// Routes under /v4/* that ship their own full-viewport chrome and must
// NOT be wrapped in the legacy V4Shell (which would double up mastheads
// and break layout). The new chat workspace at /v4/chat owns its own
// top bar, theme, sidebar, and cost badge.
const OWN_CHROME = ["/v4/chat"];

export default function V4Layout({ children }: { children: ReactNode }) {
  const pathname = usePathname() || "";
  const skipShell = OWN_CHROME.some((r) => pathname === r || pathname.startsWith(r + "/"));

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
