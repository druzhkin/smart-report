import { DocView } from "./DocView";

interface Props {
  params: Promise<{ id: string }>;
}

export default async function DocPage({ params }: Props) {
  const { id } = await params;
  return <DocView sessionId={id} />;
}
