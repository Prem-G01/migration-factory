"use client";

import { Search } from "lucide-react";
import { useUIStore } from "@/hooks/use-ui-store";
import { useHealth } from "@/hooks/use-migration-queries";
import { cn } from "@/lib/utils";

export function Header() {
  const { setCommandPaletteOpen } = useUIStore();
  const { data, isError, isLoading } = useHealth();

  const statusColor = isLoading
    ? "bg-muted-foreground"
    : isError
      ? "bg-destructive"
      : data?.status === "ok"
        ? "bg-[var(--chart-2)]"
        : "bg-destructive";

  return (
    <header className="flex h-14 shrink-0 items-center gap-4 border-b border-white/5 bg-black/10 px-6 backdrop-blur-sm">
      <button
        onClick={() => setCommandPaletteOpen(true)}
        className="flex w-72 items-center gap-2 rounded-lg border border-white/10 bg-white/[0.03] px-3 py-1.5 text-left text-sm text-muted-foreground transition-colors hover:border-white/20"
      >
        <Search className="size-3.5" />
        <span className="flex-1">Search or jump to...</span>
        <kbd className="rounded border border-white/10 bg-white/5 px-1.5 py-0.5 font-mono text-[10px]">
          ⌘K
        </kbd>
      </button>

      <div className="ml-auto flex items-center">
        {/* Dot only, no text label — established preference: the color
         * alone (green=ok, red=offline) is enough, a text badge is
         * clutter. */}
        <span
          className={cn("size-1.5 rounded-full", statusColor)}
          title={data?.status === "ok" ? "API connected" : "API unreachable"}
        />
      </div>
    </header>
  );
}
