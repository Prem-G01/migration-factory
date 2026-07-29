"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboard, History, UploadCloud, Factory } from "lucide-react";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { href: "/", label: "Analyze", icon: UploadCloud },
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/history", label: "History", icon: History },
] as const;

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="flex w-56 shrink-0 flex-col border-r border-white/5 bg-black/20 backdrop-blur-sm">
      <div className="flex items-center gap-2 px-5 py-5">
        <div className="flex size-7 items-center justify-center rounded-lg bg-gradient-to-br from-blue-500 to-cyan-400">
          <Factory className="size-4 text-white" />
        </div>
        <div>
          <div className="text-sm leading-none font-semibold">
            Migration Factory
          </div>
          <div className="mt-0.5 font-mono text-[10px] text-muted-foreground">
            AI
          </div>
        </div>
      </div>

      <nav className="flex flex-col gap-1 px-3">
        {NAV_ITEMS.map((item) => {
          const active =
            item.href === "/"
              ? pathname === "/" || pathname.startsWith("/results")
              : pathname.startsWith(item.href);
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors",
                active
                  ? "bg-primary/10 text-primary"
                  : "text-muted-foreground hover:bg-white/5 hover:text-foreground",
              )}
            >
              <Icon className="size-4" />
              {item.label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
