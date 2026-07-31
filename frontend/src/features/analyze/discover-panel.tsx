"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { useDiscoverAws } from "@/hooks/use-migration-queries";
import type { DiscoverResponse } from "@/types/migration";

interface DiscoverPanelProps {
  onDiscovered: (data: DiscoverResponse) => void;
  discovered: DiscoverResponse | null;
}

export function DiscoverPanel({ onDiscovered, discovered }: DiscoverPanelProps) {
  const [region, setRegion] = useState("ap-south-1");
  const discoverMutation = useDiscoverAws();

  const handleDiscover = async () => {
    try {
      const data = await discoverMutation.mutateAsync(region);
      onDiscovered(data);
    } catch {
      // surfaced via discoverMutation.error below
    }
  };

  return (
    <div className="flex flex-col gap-3">
      <div>
        <label className="mb-2 block font-mono text-xs tracking-wider text-muted-foreground uppercase">
          AWS Region
        </label>
        <input
          value={region}
          onChange={(e) => setRegion(e.target.value)}
          placeholder="ap-south-1"
          className="w-full rounded-lg border border-[var(--glass-border)] bg-[var(--glass-1)] px-3 py-2.5 font-mono text-sm text-foreground outline-none placeholder:text-muted-foreground/50 focus:border-[var(--yellow)]/50"
        />
      </div>

      {discovered && (
        <div className="animate-fade-up rounded-xl border border-[rgba(245,158,11,0.2)] bg-[rgba(245,158,11,0.05)] p-4">
          <div className="font-mono text-3xl font-semibold text-[var(--yellow)]">
            {discovered.resources_discovered}
          </div>
          <div className="font-mono text-xs text-muted-foreground">
            resources · {region}
          </div>
          <div className="mt-1 font-mono text-[11px] text-muted-foreground/70">
            {discovered.resource_types?.length ?? 0} resource types
          </div>
        </div>
      )}

      {discoverMutation.isError && (
        <p className="rounded-lg border border-destructive/20 bg-destructive/5 px-3 py-2 text-sm text-destructive">
          {discoverMutation.error.message}
        </p>
      )}

      <Button
        onClick={handleDiscover}
        disabled={discoverMutation.isPending}
        variant="outline"
        className="h-11 border-[var(--yellow)]/30 text-[var(--yellow)] hover:bg-[var(--yellow)]/10"
      >
        {discoverMutation.isPending ? "⏳ Discovering···" : "Discover Infrastructure"}
      </Button>
    </div>
  );
}
