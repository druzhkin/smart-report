import { redirect } from "next/navigation";

// /v4/new redirects to /v4/chat (split-workspace v4 UI).
export default async function V4NewRedirect({
  searchParams,
}: {
  searchParams: Promise<{ q?: string }>;
}) {
  const { q } = await searchParams;
  redirect(q ? `/v4/chat?q=${encodeURIComponent(q)}` : "/v4/chat");
}
