import "./globals.css";
import type { Metadata } from "next";
import { ThemeToggle } from "@/components/ThemeToggle";
import { ActivePipeline } from "@/components/ActivePipeline";
import Link from "next/link";
import { FolderOpen, PenSquare, Settings as SettingsIcon, Globe } from "lucide-react";

export const metadata: Metadata = {
  title: "Smart Report — Deep Research Studio",
  description: "Персональный глубокий аналитический движок",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ru" suppressHydrationWarning>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Newsreader:opsz,wght@6..72,400;6..72,500;6..72,600&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="min-h-screen antialiased flex flex-col md:flex-row overflow-x-hidden relative">
        <script
          dangerouslySetInnerHTML={{
            __html: `try{const t=localStorage.getItem('theme');if(t==='dark'||(!t&&window.matchMedia('(prefers-color-scheme: dark)').matches)){document.documentElement.classList.add('dark')}}catch(e){}`,
          }}
        />

        <div className="fixed top-[-20%] left-[-10%] w-[50%] h-[50%] rounded-full bg-blue-300/10 blur-[120px] pointer-events-none z-0" />
        <div className="fixed bottom-[-20%] right-[-10%] w-[50%] h-[50%] rounded-full bg-indigo-300/10 blur-[120px] pointer-events-none z-0" />

        <aside
          className="w-full md:w-64 flex-shrink-0 flex flex-col h-auto md:h-screen sticky top-0 z-20 backdrop-blur-xl border-r"
          style={{ background: "color-mix(in srgb, var(--card) 80%, transparent)", borderColor: "var(--border)" }}
        >
          <div className="p-6 pb-2">
            <Link href="/" className="text-sm font-semibold tracking-tighter uppercase flex items-center gap-2">
              <Globe size={16} />
              Smart Report
            </Link>
          </div>

          <nav className="flex-1 px-4 py-4 space-y-1">
            <NavLink href="/new" icon={<PenSquare size={18} />}>Новый запрос</NavLink>
            <NavLink href="/library" icon={<FolderOpen size={18} />}>Библиотека</NavLink>
            <NavLink href="/settings" icon={<SettingsIcon size={18} />}>Настройки</NavLink>
          </nav>

          <ActivePipeline />

          <div className="px-4 py-4 border-t flex items-center justify-between" style={{ borderColor: "var(--border)" }}>
            <span className="text-xs muted">Тема</span>
            <ThemeToggle />
          </div>
        </aside>

        <main className="flex-1 flex flex-col min-w-0 relative z-10">
          {children}
        </main>
      </body>
    </html>
  );
}

function NavLink({ href, icon, children }: { href: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <Link
      href={href}
      className="flex items-center gap-3 px-3 py-2 text-sm font-medium rounded-md transition-colors hover:bg-zinc-100/80 text-zinc-600 hover:text-zinc-900"
    >
      <span className="text-zinc-500">{icon}</span>
      {children}
    </Link>
  );
}
