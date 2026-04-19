import { redirect } from "next/navigation";

// /v4/new redirects to /v4/chat (split-workspace v4 UI).
export default function V4NewRedirect({
  searchParams,
}: {
  searchParams: { q?: string };
}) {
  const q = searchParams?.q;
  redirect(q ? `/v4/chat?q=${encodeURIComponent(q)}` : "/v4/chat");
}
