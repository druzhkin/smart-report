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
      ],
      fallback: [],
    };
  },
};

export default nextConfig;
