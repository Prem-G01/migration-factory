"use client";

import { motion } from "motion/react";
import { COLORS } from "@/constants/theme";
import type { MigrationWave } from "@/types/migration";

function formatDuration(hours: number): string {
  return hours < 1 ? `${Math.round(hours * 60)}m` : `${hours.toFixed(1)}h`;
}

export function WaveTimeline({ waves }: { waves: MigrationWave[] }) {
  return (
    <div className="relative">
      <div
        className="absolute top-5 bottom-5 left-[15px] w-px"
        style={{ background: "rgba(99,179,237,0.15)" }}
      />
      <div className="flex flex-col gap-2">
        {waves.map((wave, i) => (
          <motion.div
            key={wave.wave_number}
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.3, delay: i * 0.04 }}
            className="relative z-10 flex items-center gap-3 rounded-lg border border-white/5 bg-white/[0.02] px-3 py-2.5"
          >
            <div className="flex size-[30px] shrink-0 items-center justify-center rounded-full border border-primary/25 bg-primary/10 font-mono text-xs text-primary">
              {wave.wave_number}
            </div>
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm text-foreground/90">
                {wave.name}
              </div>
              <div className="font-mono text-[11px] text-muted-foreground">
                {wave.resource_ids.length} resources
              </div>
            </div>
            <span
              className="rounded-full border px-2 py-0.5 font-mono text-[10px]"
              style={{
                color: wave.can_parallelize ? COLORS.accentGreen : COLORS.accentYellow,
                borderColor: wave.can_parallelize
                  ? "rgba(52,211,153,0.25)"
                  : "rgba(251,191,36,0.25)",
                background: wave.can_parallelize
                  ? "rgba(52,211,153,0.08)"
                  : "rgba(251,191,36,0.08)",
              }}
            >
              {wave.can_parallelize ? "⚡ Parallel" : "→ Sequential"}
            </span>
            <span className="font-mono text-[11px] text-muted-foreground">
              {formatDuration(wave.estimated_duration_hours)}
            </span>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
