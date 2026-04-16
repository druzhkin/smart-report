"use client";

import { usePathname } from "next/navigation";
import Link from "next/link";
import { FolderOpen, PenSquare, Settings as SettingsIcon, Globe } from "lucide-react";
import { ThemeToggle } from "@/components/ThemeToggle";
import { ActivePipeline } from "@/components/ActivePipeline";

const MARKETING_ROUTES = ["/login", "/verify"];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() || "/";
  const isMarketing = MARKETING_ROUTES.some((r) => pathname === r || pathname.startsWith(r + "/"));

  if (isMarketing) {
    return <main className="flex-1 flex flex-col min-w-0 relative z-10">{children}</main>;
  }

  return (
    <>
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

      <main className="flex-1 flex flex-col min-w-0 relative z-10">{children}</main>
    </>
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
