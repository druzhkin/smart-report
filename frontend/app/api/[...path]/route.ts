// Catch-all proxy /api/* → FastAPI backend on 127.0.0.1:8000.
//
// Replaces the next.config.mjs rewrite for /api/* — that mechanism silently
// drops multipart/form-data uploads in production (POST never reaches FastAPI).
// This explicit Node-runtime proxy passes any body type through with
// streaming, supports SSE, and has a 10-min timeout matching the v4 cycle's
// worst-case wall (per A14 — Sonnet synth can run 9-15min on big prompts).

import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";        // multipart needs Node, not Edge
export const dynamic = "force-dynamic";
export const maxDuration = 600;

// Server-side proxy target — must be a real URL. Empty string would break
// fetch(). `||` keeps localhost fallback when Dockerfile sets the env to
// empty string (which it does to force CLIENT-side relative URLs in apiV4.ts).
const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";
const PROXY_TIMEOUT_MS = 10 * 60 * 1000;

const STRIP_REQ = new Set([
  "host", "connection", "transfer-encoding", "content-length",
  "x-forwarded-for", "x-forwarded-host", "x-forwarded-proto",
  "x-real-ip", "x-vercel-id", "x-vercel-deployment-url",
]);
const STRIP_RES = new Set([
  "transfer-encoding", "connection", "keep-alive",
  "content-encoding", "content-length",
]);

function pickRequestHeaders(req: NextRequest): Record<string, string> {
  const out: Record<string, string> = {};
  req.headers.forEach((v, k) => {
    if (!STRIP_REQ.has(k.toLowerCase())) out[k] = v;
  });
  return out;
}

function pickResponseHeaders(headers: Headers): Headers {
  const out = new Headers();
  headers.forEach((v, k) => {
    if (!STRIP_RES.has(k.toLowerCase())) out.set(k, v);
  });
  return out;
}

async function proxy(
  req: NextRequest,
  ctx: { params: { path: string[] } }
): Promise<Response> {
  const path = (ctx.params.path || []).join("/");
  const search = req.nextUrl.search || "";
  const target = `${API_BASE}/api/${path}${search}`;

  const ctrl = new AbortController();
  const tid = setTimeout(() => ctrl.abort(), PROXY_TIMEOUT_MS);

  try {
    const hasBody = !["GET", "HEAD"].includes(req.method);
    const upstream = await fetch(target, {
      method: req.method,
      headers: pickRequestHeaders(req),
      body: hasBody ? (req.body as any) : undefined,
      // @ts-expect-error duplex required when streaming a request body in Node
      duplex: hasBody ? "half" : undefined,
      signal: ctrl.signal,
      redirect: "manual",
    });
    clearTimeout(tid);

    return new NextResponse(upstream.body, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: pickResponseHeaders(upstream.headers),
    });
  } catch (err: any) {
    clearTimeout(tid);
    const reason = err?.name === "AbortError" ? "proxy timeout (10min)" : (err?.message || String(err));
    return NextResponse.json(
      { detail: `proxy error: ${reason}`, target },
      { status: 502 }
    );
  }
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const DELETE = proxy;
export const PATCH = proxy;
