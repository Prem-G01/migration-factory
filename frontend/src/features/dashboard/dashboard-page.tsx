"use client";

import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { GlassCard } from "@/components/ui/glass-card";
import { MetricCard } from "@/components/ui/metric-card";
import { EmptyState } from "@/components/ui/empty-state";
import { Section } from "@/components/ui/section";
import { Skeleton } from "@/components/ui/skeleton";
import { DistributionBars, type DistributionEntry } from "@/components/data/distribution-bars";
import { DataTable, type DataTableColumn } from "@/components/data/data-table";
import { useRuns } from "@/hooks/use-migration-queries";
import { COLORS, RISK_COLORS, directionColor } from "@/constants/theme";
import type { RunListItem } from "@/types/migration";

export function DashboardPage() {
  const router = useRouter();
  const { data, isLoading } = useRuns();
  const runs = data?.runs ?? [];
  const total = runs.length;

  if (isLoading) {
    return (
      <div className="flex flex-col gap-4 p-8">
        <Skeleton className="h-8 w-48" />
        <div className="grid grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-28 rounded-xl" />
          ))}
        </div>
      </div>
    );
  }

  if (total === 0) {
    return (
      <EmptyState
        icon="🌌"
        message="No analyses yet."
        action={
          <Button onClick={() => router.push("/")} className="mt-2">
            Start Analyzing →
          </Button>
        }
      />
    );
  }

  const totalResources = runs.reduce((sum, r) => sum + (r.resources ?? 0), 0);
  const totalSavings = runs.reduce((sum, r) => sum + (r.monthly_savings ?? 0), 0);
  const avgDuration = runs.reduce((sum, r) => sum + (r.duration_seconds ?? 0), 0) / total;

  const riskCounts = new Map<string, number>();
  for (const r of runs) {
    if (r.risk_level) riskCounts.set(r.risk_level, (riskCounts.get(r.risk_level) ?? 0) + 1);
  }
  const riskEntries: DistributionEntry[] = Array.from(riskCounts.entries()).map(
    ([label, count]) => ({ label, count, color: RISK_COLORS[label] ?? COLORS.muted }),
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

  const columns: DataTableColumn<RunListItem>[] = [
    {
      key: "direction",
      header: "Direction",
      render: (r) => (
        <span
          className="rounded-full px-2.5 py-1 font-mono text-xs"
          style={{ color: directionColor(r.direction), background: `${directionColor(r.direction)}14` }}
        >
          {r.direction || "Analysis"}
        </span>
      ),
    },
    {
      key: "resources",
      header: "Resources",
      align: "right",
      render: (r) => <span className="font-mono text-muted-foreground">{r.resources ?? "—"}</span>,
    },
    {
      key: "risk",
      header: "Risk",
      render: (r) =>
        r.risk_level ? (
          <span className="font-mono text-sm font-semibold" style={{ color: RISK_COLORS[r.risk_level] }}>
            {r.risk_level.toUpperCase()}
          </span>
        ) : (
          "—"
        ),
    },
    {
      key: "savings",
      header: "Savings",
      align: "right",
      render: (r) => (
        <span className="font-mono text-[var(--green)]">
          {r.monthly_savings != null ? `$${r.monthly_savings}/mo` : "—"}
        </span>
      ),
    },
    {
      key: "actions",
      header: "",
      align: "right",
      render: (r) => (
        <button
          onClick={() => router.push(`/?run=${r.run_id}`)}
          className="rounded-md border border-white/10 px-3 py-1 text-xs font-medium text-primary transition-colors hover:bg-primary/10"
        >
          View
        </button>
      ),
    },
  ];

  return (
    <div className="flex h-full flex-col gap-6 overflow-y-auto p-8">
      <div className="animate-fade-up flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Dashboard</h1>
          <span className="font-mono text-xs text-muted-foreground">{total} total analyses</span>
        </div>
        <Button variant="outline" onClick={() => router.push("/")}>
          + New Analysis
        </Button>
      </div>

      <Section index={0}>
        <div className="grid grid-cols-4 gap-4">
          <MetricCard label="Total Analyses" value={total} sub="all time" color={COLORS.cyan} />
          <MetricCard label="Resources Analyzed" value={totalResources} sub="across all runs" color={COLORS.purple} />
          <MetricCard label="Total Savings" value={Math.round(totalSavings)} prefix="$" sub="per month if migrated" color={COLORS.green} />
          <MetricCard label="Avg Duration" value={Number(avgDuration.toFixed(1))} suffix="s" sub="per analysis" color={COLORS.yellow} />
        </div>
      </Section>

      <div className="grid grid-cols-2 gap-4">
        <Section title="Risk Distribution" index={1}>
          <GlassCard hoverElevate={false}>
            <DistributionBars entries={riskEntries} total={total} />
          </GlassCard>
        </Section>
        <Section title="Use Case Breakdown" index={2}>
          <GlassCard hoverElevate={false}>
            <DistributionBars entries={dirEntries} total={maxDirCount} />
          </GlassCard>
        </Section>
      </div>

      <Section title={`Recent Analyses (${Math.min(6, runs.length)})`} index={3}>
        <DataTable
          columns={columns}
          rows={runs.slice(0, 6)}
          getRowKey={(r) => r.run_id}
          getRowAccent={(r) => directionColor(r.direction)}
        />
      </Section>
    </div>
  );
}
