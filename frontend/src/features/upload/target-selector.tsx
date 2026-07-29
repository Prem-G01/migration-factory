"use client";

import { useState } from "react";
import { TARGET_OPTIONS } from "@/constants/upload";
import type { MigrationTarget } from "@/types/migration";
import { cn } from "@/lib/utils";

interface TargetSelectorProps {
  value: MigrationTarget;
  onChange: (target: MigrationTarget) => void;
  /** Restrict to a subset — the Discover Live panel only supports
   * gcp/aws (a live-discovered estate always has a known source cloud,
   * so "analyze only" doesn't apply the same way). */
  options?: MigrationTarget[];
}

export function TargetSelector({ value, onChange, options }: TargetSelectorProps) {
  const [hovered, setHovered] = useState<MigrationTarget | null>(null);
  const visible = options
    ? TARGET_OPTIONS.filter((t) => options.includes(t.value))
    : TARGET_OPTIONS;
  const activeDescription = TARGET_OPTIONS.find((t) => t.value === (hovered ?? value))
    ?.description;

  return (
    <div>
      <div className="mb-2 font-mono text-[10px] tracking-wider text-muted-foreground uppercase">
        Migration Target
      </div>
      <div
        className="grid gap-1.5"
        style={{ gridTemplateColumns: `repeat(${visible.length}, 1fr)` }}
      >
        {visible.map((option) => {
          const selected = value === option.value;
          return (
            <button
              key={option.value}
              type="button"
              onClick={() => onChange(option.value)}
              onMouseEnter={() => setHovered(option.value)}
              onMouseLeave={() => setHovered((h) => (h === option.value ? null : h))}
              className={cn(
                "rounded-lg border px-2.5 py-2.5 text-left transition-colors",
                selected
                  ? "border-white/20 bg-white/[0.04]"
                  : "border-white/10 bg-white/[0.02] hover:border-white/15",
              )}
              style={selected ? { borderColor: `${option.color}59` } : undefined}
            >
              <div
                className="font-mono text-[10px]"
                style={{ color: selected ? option.color : "var(--color-muted-foreground)" }}
              >
                {option.label}
              </div>
              <div
                className={cn(
                  "mt-0.5 text-xs font-medium",
                  selected ? "text-foreground" : "text-muted-foreground",
                )}
              >
                {option.name}
              </div>
            </button>
          );
        })}
      </div>
      <div className="mt-1.5 min-h-[30px]">
        {activeDescription && (
          <p className="rounded-lg border border-white/10 bg-white/[0.03] px-2.5 py-1.5 text-xs text-muted-foreground">
            {activeDescription}
          </p>
        )}
      </div>
    </div>
  );
}
