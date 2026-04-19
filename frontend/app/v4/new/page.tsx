import { redirect } from "next/navigation";

// /v4/new is the legacy entry for the 6-screen wizard. The flow has moved to
// /v4/chat (full chat UI). Preserve any question passed via ?q= so links keep
// working.
export default function V4NewRedirect({
  searchParams,
}: {
  searchParams: { q?: string };
}) {
  const q = searchParams?.q;
  redirect(q ? `/v4/chat?q=${encodeURIComponent(q)}` : "/v4/chat");
}
