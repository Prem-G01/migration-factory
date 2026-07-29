"use client";

import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { GlassCard } from "@/components/ui/glass-card";
import { MetricCard } from "@/components/ui/metric-card";
import { EmptyState } from "@/components/ui/empty-state";
import { Section } from "@/components/ui/section";
import { Skeleton } from "@/components/ui/skeleton";
import { DistributionBars, type DistributionEntry } from "@/components/data/distribution-bars";
import { useRuns } from "@/hooks/use-migration-queries";
import { COLORS, RISK_COLORS, directionColor } from "@/constants/theme";

export function DashboardPage() {
  const router = useRouter();
  const { data, isLoading } = useRuns();
  const runs = data?.runs ?? [];
  const total = runs.length;

  if (isLoading) {
    return (
      <div className="flex flex-col gap-4 p-6">
        <Skeleton className="h-8 w-48" />
        <div className="grid grid-cols-4 gap-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-24 rounded-xl" />
          ))}
        </div>
      </div>
    );
  }

  if (total === 0) {
    return (
      <EmptyState
        icon="📊"
        message="No analyses yet. Run your first analysis to see statistics here."
        action={
          <Button onClick={() => router.push("/")}>Start Analyzing →</Button>
        }
      />
    );
  }

  const totalResources = runs.reduce((sum, r) => sum + (r.resources ?? 0), 0);
  const totalSavings = runs.reduce((sum, r) => sum + (r.monthly_savings ?? 0), 0);
  const avgDuration = runs.reduce((sum, r) => sum + (r.duration_seconds ?? 0), 0) / total;

  const riskCounts = new Map<string, number>();
  for (const r of runs) {
    if (r.risk_level) {
      riskCounts.set(r.risk_level, (riskCounts.get(r.risk_level) ?? 0) + 1);
    }
  }
  const riskEntries: DistributionEntry[] = Array.from(riskCounts.entries()).map(
    ([label, count]) => ({ label, count, color: RISK_COLORS[label] ?? COLORS.textMuted }),
  );

  const dirCounts = new Map<string, number>();
  for (const r of runs) {
    const d = r.direction || "Unknown";
    dirCounts.set(d, (dirCounts.get(d) ?? 0) + 1);
  }
  const dirEntries: DistributionEntry[] = Array.from(dirCounts.entries()).map(
    ([label, count]) => ({ label, count, color: directionColor(label) }),
  );
  const maxDirCount = Math.max(...dirEntries.map((e) => e.count), 1);

  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold">Dashboard</h1>
          <span className="font-mono text-[11px] text-muted-foreground">
            {total} total analyses
          </span>
        </div>
        <Button variant="outline" onClick={() => router.push("/")}>
          + New Analysis
        </Button>
      </div>

      <Section index={0}>
        <div className="grid grid-cols-4 gap-3">
          <MetricCard label="Total Analyses" value={total} sub="all time" color={COLORS.accentCyan} />
          <MetricCard label="Resources Analyzed" value={totalResources} sub="across all runs" color={COLORS.accentPurple} />
          <MetricCard label="Total Savings" value={Math.round(totalSavings)} prefix="$" sub="per month if migrated" color={COLORS.accentGreen} />
          <MetricCard label="Avg Duration" value={Number(avgDuration.toFixed(1))} suffix="s" sub="per analysis" color={COLORS.accentYellow} />
        </div>
      </Section>

      <div className="grid grid-cols-2 gap-4">
        <Section title="Risk Distribution" index={1}>
          <GlassCard hoverElevate={false}>
            <DistributionBars entries={riskEntries} total={total} />
          </GlassCard>
        </Section>
        <Section title="Migration Directions" index={2}>
          <GlassCard hoverElevate={false}>
            <DistributionBars entries={dirEntries} total={maxDirCount} />
          </GlassCard>
        </Section>
      </div>

      <Section title={`Recent Analyses (${Math.min(6, runs.length)})`} index={3}>
        <GlassCard hoverElevate={false} className="p-0">
          {runs.slice(0, 6).map((run, i) => {
            const color = directionColor(run.direction);
            return (
              <button
                key={run.run_id}
                onClick={() => router.push(`/results?run=${run.run_id}`)}
                className={`flex w-full items-center gap-3 px-4 py-2.5 text-left transition-colors hover:bg-white/[0.03] ${
                  i < Math.min(6, runs.length) - 1 ? "border-b border-white/5" : ""
                }`}
              >
                <span
                  className="size-2 shrink-0 rounded-full"
                  style={{ background: color, boxShadow: `0 0 6px ${color}` }}
                />
                <span
                  className="shrink-0 rounded-full px-2 py-0.5 font-mono text-[10px]"
                  style={{ color, background: `${color}14` }}
                >
                  {run.direction || "Analysis"}
                </span>
                <span className="flex-1 text-xs text-muted-foreground">
                  {run.resources ?? 0} resources
                </span>
                <span
                  className="font-mono text-[11px]"
                  style={{ color: RISK_COLORS[run.risk_level] ?? COLORS.textMuted }}
                >
                  {run.risk_level?.toUpperCase() ?? "—"}
                </span>
                <span className="font-mono text-xs text-[#34d399]">
                  ${run.monthly_savings ?? 0}/mo
                </span>
                <span className="font-mono text-[11px] text-muted-foreground">
                  {run.duration_seconds?.toFixed(1)}s
                </span>
                <span className="font-mono text-[11px] text-primary">View →</span>
              </button>
            );
          })}
        </GlassCard>
      </Section>
    </div>
  );
}
