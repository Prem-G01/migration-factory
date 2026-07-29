import type { ReactNode } from "react";
import { GlassCard } from "@/components/ui/glass-card";
import { AnimatedCounter } from "@/components/ui/animated-counter";
import { cn } from "@/lib/utils";

interface MetricCardProps {
  label: string;
  /** Numeric value animates via AnimatedCounter. Pass a string (e.g. a
   * risk-level label) to render it statically instead. */
  value: number | string;
  prefix?: string;
  suffix?: string;
  sub?: string;
  color?: string;
  icon?: ReactNode;
  className?: string;
}

export function MetricCard({
  label,
  value,
  prefix,
  suffix,
  sub,
  color = "var(--color-primary)",
  icon,
  className,
}: MetricCardProps) {
  return (
    <GlassCard accent={color} className={cn("flex flex-col gap-1", className)}>
      <div className="flex items-center justify-between">
        <span className="font-mono text-xs uppercase tracking-wider text-muted-foreground">
          {label}
        </span>
        {icon && (
          <span className="text-muted-foreground/60" style={{ color }}>
            {icon}
          </span>
        )}
      </div>
      <div
        className="font-mono text-[32px] leading-none font-bold"
        style={{ color }}
      >
        {typeof value === "number" ? (
          <AnimatedCounter value={value} prefix={prefix} suffix={suffix} />
        ) : (
          <span>{value}</span>
        )}
      </div>
      {sub && <div className="text-[13px] text-muted-foreground">{sub}</div>}
    </GlassCard>
  );
}
