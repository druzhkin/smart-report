/** @type {import('next').NextConfig} */
const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

const nextConfig = {
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
