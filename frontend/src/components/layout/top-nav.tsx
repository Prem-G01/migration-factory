"use client";

import { useEffect } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Factory, LayoutDashboard, Sparkles } from "lucide-react";
import { useHealth } from "@/hooks/use-migration-queries";
import { ThemeToggle } from "@/components/layout/theme-toggle";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { href: "/", label: "Analyze", key: "a", icon: Sparkles },
  { href: "/dashboard", label: "Dashboard", key: "d", icon: LayoutDashboard },
] as const;

/** Broadcast so the Analyze page's in-progress wizard state resets even
 * when we're already on "/" — a plain Link can't force that by itself. */
export function goHome() {
  window.dispatchEvent(new Event("mf:go-home"));
}

export function TopNav() {
  const pathname = usePathname();
  const router = useRouter();
  const { data, isLoading, isError } = useHealth();

  // 'a' -> Analyze, 'd' -> Dashboard. Ignored while typing in a form
  // field so e.g. the region input's "d" characters don't hijack nav.
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      const tag = document.activeElement?.tagName;
      const typing =
        tag === "INPUT" || tag === "TEXTAREA" || document.activeElement?.hasAttribute("contenteditable");
      if (typing) return;

      if (e.key === "a") router.push("/");
      else if (e.key === "d") router.push("/dashboard");
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [router]);

  const statusColor = isLoading
    ? "bg-[var(--dim)]"
    : isError || data?.status !== "ok"
      ? "bg-[var(--red)]"
      : "bg-[var(--green)]";
  const statusLabel = isLoading ? "Connecting…" : isError || data?.status !== "ok" ? "API unreachable" : "API connected";

  return (
    <header className="relative z-10 flex h-16 shrink-0 items-center gap-4 border-b border-[var(--glass-border-soft)] bg-[var(--nav-bg)] px-4 backdrop-blur-xl sm:px-6">
      <button
        type="button"
        onClick={() => {
          goHome();
          router.push("/");
        }}
        title="Home"
        className="group flex items-center gap-2.5"
      >
        <div className="flex size-8 items-center justify-center rounded-lg bg-gradient-to-br from-[var(--cyan)] to-[#0066ff] shadow-[0_2px_10px_-2px_rgba(0,153,255,0.5)] transition-transform group-hover:scale-105">
          <Factory className="size-4 text-white" />
        </div>
        <div className="hidden items-baseline gap-2 sm:flex">
          <span className="text-base font-semibold">Migration Factory</span>
          <span className="font-mono text-[11px] text-muted-foreground">v2.0.3</span>
        </div>
      </button>

      <nav className="mx-auto flex gap-1 rounded-full border border-[var(--glass-border)] bg-[var(--glass-1)] p-1">
        {NAV_ITEMS.map((item) => {
          const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-sm font-medium transition-colors sm:px-4",
                active
                  ? "bg-primary text-primary-foreground shadow-[0_0_16px_-2px_var(--cyan)]"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              <Icon className="size-3.5" />
              <span className="hidden sm:inline">{item.label}</span>
            </Link>
          );
        })}
      </nav>

      <div className="ml-auto flex items-center gap-2">
        <span
          className="hidden items-center gap-1.5 rounded-full border border-[var(--glass-border)] bg-[var(--glass-1)] px-2.5 py-1 font-mono text-[10px] tracking-wide text-muted-foreground uppercase md:flex"
          title={statusLabel}
        >
          <span className={cn("size-1.5 rounded-full", statusColor)} />
          {statusLabel}
        </span>
        <ThemeToggle />
      </div>
    </header>
  );
}
