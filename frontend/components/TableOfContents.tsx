"use client";

import { useEffect, useState } from "react";
import { List } from "lucide-react";

export type TocItem = {
  id: string;
  label: string;
  sub?: { id: string; label: string }[];
};

export function TableOfContents({ items }: { items: TocItem[] }) {
  const [active, setActive] = useState<string>(items[0]?.id ?? "");

  useEffect(() => {
    const ids = items.flatMap((i) => [i.id, ...(i.sub?.map((s) => s.id) ?? [])]);
    const els = ids.map((id) => document.getElementById(id)).filter(Boolean) as HTMLElement[];
    if (els.length === 0) return;
    const obs = new IntersectionObserver(
      (entries) => {
        const visible = entries.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible[0]?.target?.id) setActive(visible[0].target.id);
      },
      { rootMargin: "-20% 0px -70% 0px", threshold: 0 }
    );
    els.forEach((el) => obs.observe(el));
    return () => obs.disconnect();
  }, [items]);

  function jump(id: string) {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  return (
    <div
      className="p-5 rounded-xl backdrop-blur-md max-h-[calc(100vh-8rem)] overflow-y-auto"
      style={{
        background: "color-mix(in srgb, var(--card) 80%, transparent)",
        border: "1px solid var(--border)",
        boxShadow: "0 8px 30px rgb(0 0 0 / 0.04)",
      }}
    >
      <h4 className="text-xs font-semibold uppercase tracking-widest mb-4 flex items-center gap-2">
        <List size={14} />
        Contents
      </h4>
      <nav className="relative space-y-1">
        <div className="absolute inset-y-0 left-1.5 w-px" style={{ background: "var(--border)" }} />
        {items.map((it) => {
          const isActive = active === it.id;
          return (
            <div key={it.id}>
              <button
                type="button"
                onClick={() => jump(it.id)}
                className="relative flex items-center gap-3 py-1.5 pl-5 text-sm font-medium transition-colors w-full text-left hover:opacity-80"
                style={{ color: isActive ? "var(--accent)" : "var(--muted)" }}
              >
                <span
                  className="absolute rounded-full z-10"
                  style={
                    isActive
                      ? { left: 0, top: "50%", transform: "translateY(-50%)", width: 12, height: 12, background: "var(--card)", border: "2px solid var(--accent)", boxShadow: "0 0 0 3px color-mix(in srgb, var(--accent) 20%, transparent)" }
                      : { left: 4, top: "50%", transform: "translateY(-50%)", width: 6, height: 6, background: "var(--border)" }
                  }
                />
                <span className="truncate">{it.label}</span>
              </button>
              {it.sub && it.sub.length > 0 && (
                <div className="pl-8 space-y-1 my-1">
                  {it.sub.map((s) => (
                    <button
                      key={s.id}
                      type="button"
                      onClick={() => jump(s.id)}
                      className="block py-1 text-xs truncate transition-colors w-full text-left hover:opacity-80"
                      style={{ color: active === s.id ? "var(--fg)" : "var(--muted)" }}
                    >
                      {s.label}
                    </button>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </nav>
    </div>
  );
}
