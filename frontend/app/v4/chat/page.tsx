"use client";

// /v4/chat — Smart Report v.IV split-workspace chat UI
// Full mock-mode. Backend integration: future iteration.
//
// SSR is disabled for Workspace: the component reads localStorage in
// useState initializers (theme, messages, phase, cost, title, expanded
// projects) — rendering it on the server produces a tree that disagrees
// with the client's first paint, causing hydration mismatches
// (most visibly on the theme-toggle <circle>). For a heavily client-stateful
// dashboard there is no SEO value in SSR, so we opt out.

import dynamic from "next/dynamic";

const Workspace = dynamic(() => import("./Workspace"), {
  ssr: false,
  loading: () => (
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
      загружаем…
    </div>
  ),
});

export default function V4ChatPage() {
  return <Workspace />;
}
