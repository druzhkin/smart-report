import { redirect } from "next/navigation";

// /v4/new redirects to /v4/doc (Swiss document UI, primary v4 flow).
// /v4/chat remains for A/B testing. Pass ?q= so links keep working.
export default function V4NewRedirect({
  searchParams,
}: {
  searchParams: { q?: string };
}) {
  const q = searchParams?.q;
  redirect(q ? `/v4/doc?q=${encodeURIComponent(q)}` : "/v4/doc");
}
