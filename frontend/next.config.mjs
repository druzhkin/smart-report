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
  async rewrites() {
    return {
      beforeFiles: [
        { source: "/", destination: "/landing.html" },
      ],
      afterFiles: [
        { source: "/api/:path*", destination: `${API_BASE}/api/:path*` },
        // Railway healthcheck hits /health — proxy to FastAPI so the
        // container doesn't get killed by repeated 404s. Same for the
        // landing/app routes served by FastAPI's static router.
        { source: "/health", destination: `${API_BASE}/health` },
        { source: "/favicon.ico", destination: `${API_BASE}/favicon.ico` },
        { source: "/landing/:path*", destination: `${API_BASE}/landing/:path*` },
        { source: "/app/:path*", destination: `${API_BASE}/app/:path*` },
      ],
      fallback: [],
    };
  },
};

export default nextConfig;
