"use client";

import { motion } from "motion/react";
import { DisclosureNote } from "@/components/ui/disclosure-note";
import { EmptyState } from "@/components/ui/empty-state";
import { COLORS } from "@/constants/theme";
import type { FrameworkResult } from "@/types/migration";

function frameworkColor(pct: number): string {
  if (pct >= 80) return COLORS.green;
  if (pct >= 60) return COLORS.yellow;
  return COLORS.red;
}

export function ComplianceTab({ frameworks }: { frameworks: FrameworkResult[] }) {
  return (
    <div>
      <DisclosureNote>
        * Configuration-based checks. Not a substitute for AWS Security Hub or a
        formal compliance audit.
      </DisclosureNote>

      {frameworks.length === 0 ? (
        <EmptyState icon="📋" message="No compliance data for this run." />
      ) : (
        <div className="grid grid-cols-2 gap-3">
          {frameworks.map((f) => {
            const pct = Math.round(f.compliance_score);
            const color = frameworkColor(pct);
            return (
              <div
                key={f.framework}
                className="card-hover rounded-xl border border-white/10 bg-white/[0.02] p-4"
              >
                <div className="mb-2 flex items-center justify-between">
                  <span className="font-mono text-sm text-foreground/90">{f.framework}</span>
                  <span className="font-mono text-lg font-semibold" style={{ color }}>
                    {pct}%
                  </span>
                </div>
                <div className="h-1.5 overflow-hidden rounded-full bg-white/5">
                  <motion.div
                    className="h-full rounded-full"
                    style={{ background: color }}
                    initial={{ width: 0 }}
                    animate={{ width: `${pct}%` }}
                    transition={{ duration: 0.6, ease: "easeOut" }}
                  />
                </div>
                {f.failed_check_ids.length > 0 && (
                  <div className="mt-2 font-mono text-[11px] text-muted-foreground">
                    Failed: {f.failed_check_ids.slice(0, 2).join(", ")}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
