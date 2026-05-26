/** @type {import('next').NextConfig} */
// 127.0.0.1 vs ::1: some Node versions resolve "localhost" to IPv6 (::1) where
// uvicorn binds only to IPv4. Force 127.0.0.1 so the proxy lands on the right
// socket. Saw ECONNREFUSED ::1:8000 in Railway logs before this fix.
const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";

const nextConfig = {
  // Sonnet generate-prompt / analyze / synthesize calls can take 5-180 s
  // each (Phase 3 + A14 finding: synth alone is 9-15 min on large prompts).
  // Default Next.js rewrite proxy times out long before that — gave us
  // "socket hang up ECONNRESET" on /generate-prompt in production. 10 min
  // upper bound matches the v4 cycle's worst case per A14.
  experimental: {
    proxyTimeout: 600_000,
  },
  async redirects() {
    return [
      { source: "/new", destination: "/v4/chat", permanent: false },
      { source: "/app/:path*", destination: "/v4/chat", permanent: false },
      { source: "/login", destination: "/v4/chat", permanent: false },
      { source: "/library", destination: "/v4/chat", permanent: false },
      { source: "/settings", destination: "/v4/chat", permanent: false },
      { source: "/verify", destination: "/v4/chat", permanent: false },
      { source: "/report/:path*", destination: "/v4/chat", permanent: false },
      { source: "/v3/:path*", destination: "/v4/chat", permanent: false },
      { source: "/v4", destination: "/v4/chat", permanent: false },
      { source: "/v4/new", destination: "/v4/chat", permanent: false },
      { source: "/v4/session/:path*", destination: "/v4/chat", permanent: false },
      { source: "/v4/doc/:path*", destination: "/v4/chat", permanent: false },
    ];
  },
  async rewrites() {
    return {
      beforeFiles: [
        { source: "/", destination: "/landing.html" },
      ],
      afterFiles: [
        // /api/* now goes through frontend/app/api/[...path]/route.ts —
        // a Node-runtime catch-all proxy that handles multipart and SSE
        // properly (the rewrite mechanism silently dropped multipart
        // uploads in Railway prod). Keep ONLY non-/api paths here.
        { source: "/health", destination: `${API_BASE}/health` },
        { source: "/health/:path*", destination: `${API_BASE}/health/:path*` },
        { source: "/favicon.ico", destination: `${API_BASE}/favicon.ico` },
        { source: "/landing/:path*", destination: `${API_BASE}/landing/:path*` },
        { source: "/app/:path*", destination: `${API_BASE}/app/:path*` },
      ],
      fallback: [],
    };
  },
};

export default nextConfig;
