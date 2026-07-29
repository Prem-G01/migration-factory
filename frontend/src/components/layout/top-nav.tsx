"use client";

import { useEffect } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Factory } from "lucide-react";
import { useHealth } from "@/hooks/use-migration-queries";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { href: "/", label: "Analyze", key: "a" },
  { href: "/dashboard", label: "Dashboard", key: "d" },
] as const;

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

  return (
    <header className="relative z-10 flex h-16 shrink-0 items-center border-b border-white/5 bg-black/20 px-6 backdrop-blur-sm">
      <div className="flex items-center gap-2.5">
        <div className="flex size-8 items-center justify-center rounded-lg bg-gradient-to-br from-[var(--cyan)] to-[#0066ff]">
          <Factory className="size-4 text-black" />
        </div>
        <div className="flex items-baseline gap-2">
          <span className="text-base font-semibold">Migration Factory</span>
          <span className="font-mono text-[11px] text-muted-foreground">v2.0.3</span>
        </div>
      </div>

      <nav className="absolute left-1/2 flex -translate-x-1/2 gap-1 rounded-full border border-white/10 bg-white/[0.02] p-1">
        {NAV_ITEMS.map((item) => {
          const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "rounded-full px-4 py-1.5 text-sm font-medium transition-colors",
                active
                  ? "bg-primary/15 text-primary"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {item.label}
            </Link>
          );
        })}
      </nav>

      <div className="ml-auto flex items-center">
        <span
          className={cn("size-2 rounded-full", statusColor)}
          title={data?.status === "ok" ? "API connected" : "API unreachable"}
        />
      </div>
    </header>
  );
}
