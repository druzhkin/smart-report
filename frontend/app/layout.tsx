import "./globals.css";
import type { Metadata } from "next";
import { ThemeToggle } from "@/components/ThemeToggle";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Smart Report",
  description: "Персональный аналитический движок",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ru" suppressHydrationWarning>
      <body className="min-h-screen antialiased">
        <script
          dangerouslySetInnerHTML={{
            __html: `try{const t=localStorage.getItem('theme');if(t==='dark'||(!t&&window.matchMedia('(prefers-color-scheme: dark)').matches)){document.documentElement.classList.add('dark')}}catch(e){}`,
          }}
        />
        <header className="border-b" style={{ borderColor: "var(--border)" }}>
          <div className="max-w-7xl mx-auto px-6 py-3 flex items-center justify-between">
            <Link href="/" className="flex items-center gap-2 font-semibold">
              <span className="w-6 h-6 rounded-md" style={{ background: "var(--accent)" }} />
              Smart Report
            </Link>
            <nav className="flex items-center gap-4 text-sm">
              <Link href="/new" className="hover:underline">Новый запрос</Link>
              <Link href="/library" className="hover:underline">Библиотека</Link>
              <ThemeToggle />
            </nav>
          </div>
        </header>
        <main className="max-w-7xl mx-auto px-6 py-6">{children}</main>
      </body>
    </html>
  );
}
