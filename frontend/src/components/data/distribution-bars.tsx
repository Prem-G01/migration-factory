"use client";

import { motion } from "motion/react";

export interface DistributionEntry {
  label: string;
  count: number;
  color: string;
}

export function DistributionBars({
  entries,
  total,
}: {
  entries: DistributionEntry[];
  total: number;
}) {
  if (entries.length === 0) {
    return (
      <p className="font-mono text-xs text-muted-foreground">No data yet</p>
    );
  }

  return (
    <div className="flex flex-col gap-2.5">
      {entries.map((entry) => (
        <div key={entry.label}>
          <div className="mb-1 flex justify-between font-mono text-xs">
            <span style={{ color: entry.color }} className="uppercase">
              {entry.label}
            </span>
            <span className="text-muted-foreground">{entry.count}</span>
          </div>
          <div className="h-1 overflow-hidden rounded-full bg-[var(--glass-2)]">
            <motion.div
              className="h-full rounded-full"
              style={{ background: entry.color }}
              initial={{ width: 0 }}
              animate={{ width: `${(entry.count / total) * 100}%` }}
              transition={{ duration: 0.6, ease: "easeOut" }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}
