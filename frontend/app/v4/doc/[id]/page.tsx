import { DocView } from "./DocView";

interface Props {
  params: { id: string };
}

export default function DocPage({ params }: Props) {
  return <DocView sessionId={params.id} />;
}
