"use client";

import { useState } from "react";
import { motion } from "motion/react";
import { Button } from "@/components/ui/button";
import { TargetSelector } from "@/features/upload/target-selector";
import { useDiscoverAws } from "@/hooks/use-migration-queries";
import type { DiscoverResponse, MigrationTarget } from "@/types/migration";

interface DiscoverPanelProps {
  target: MigrationTarget;
  onTargetChange: (target: MigrationTarget) => void;
  onDiscovered: (data: DiscoverResponse) => void;
  discovered: DiscoverResponse | null;
}

export function DiscoverPanel({
  target,
  onTargetChange,
  onDiscovered,
  discovered,
}: DiscoverPanelProps) {
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
    <div className="flex flex-col gap-4">
      <div>
        <label className="mb-2 block font-mono text-[10px] tracking-wider text-muted-foreground uppercase">
          AWS Region
        </label>
        <input
          value={region}
          onChange={(e) => setRegion(e.target.value)}
          placeholder="ap-south-1"
          className="w-full rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 font-mono text-sm text-foreground outline-none placeholder:text-muted-foreground/50 focus:border-primary/40"
        />
      </div>

      {discovered && (
        <motion.div
          initial={{ opacity: 0, scale: 0.98 }}
          animate={{ opacity: 1, scale: 1 }}
          className="rounded-xl border border-[rgba(52,211,153,0.2)] bg-[rgba(52,211,153,0.05)] p-4"
        >
          <div className="font-mono text-3xl font-semibold text-[#34d399]">
            {discovered.resources_discovered}
          </div>
          <div className="font-mono text-xs text-muted-foreground">
            resources · {region}
          </div>
          <div className="mt-1 font-mono text-[11px] text-muted-foreground/70">
            {discovered.resource_types?.length ?? 0} resource types
          </div>
          <div className="mt-3">
            <TargetSelector value={target} onChange={onTargetChange} options={["gcp", "aws"]} />
          </div>
        </motion.div>
      )}

      {discoverMutation.isError && (
        <p className="rounded-lg border border-destructive/20 bg-destructive/5 px-3 py-2 text-xs text-destructive">
          {discoverMutation.error.message}
        </p>
      )}

      {!discovered && (
        <Button
          onClick={handleDiscover}
          disabled={discoverMutation.isPending}
          className="h-11"
        >
          {discoverMutation.isPending ? "⏳ Discovering···" : "🔍 Discover AWS Infrastructure"}
        </Button>
      )}
    </div>
  );
}
