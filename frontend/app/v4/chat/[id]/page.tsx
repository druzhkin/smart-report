import { CostProvider } from "@/lib/costContext";
import { ChatView } from "./ChatView";

/**
 * /v4/chat/[id] — resumable chat. Server component wrapper that hands off to
 * the client ChatView. Wrapped in a fresh CostProvider so the v4 chat route
 * doesn't depend on the old V4Shell / AppShell layouts.
 */
export default function V4ChatSessionPage({
  params,
}: {
  params: { id: string };
}) {
  return (
    <CostProvider>
      <ChatView sessionId={params.id} />
    </CostProvider>
  );
}
