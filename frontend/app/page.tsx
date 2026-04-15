import Link from "next/link";

export default function Home() {
  return (
    <div className="max-w-3xl mx-auto pt-12 space-y-6">
      <h1 className="text-3xl font-semibold">Smart Report</h1>
      <p className="muted">
        Персональный аналитический движок. Задай цель — получи приоритизированную матрицу доменов,
        проработанные блоки и кросс-доменные связи. Дирижируй исследованием, а не читай PDF.
      </p>
      <div className="flex gap-3">
        <Link href="/new" className="btn btn-primary">Новый запрос</Link>
        <Link href="/library" className="btn">Библиотека отчётов</Link>
      </div>
    </div>
  );
}
