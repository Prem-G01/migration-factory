import { DataTable, type DataTableColumn } from "@/components/data/data-table";
import { MetricCard } from "@/components/ui/metric-card";
import { EmptyState } from "@/components/ui/empty-state";
import { COLORS } from "@/constants/theme";
import type { ResourceAssessment } from "@/types/migration";

interface MappingRow {
  canonicalType: string;
  targetService: string | null;
  count: number;
}

function groupByMapping(resources: ResourceAssessment[]): MappingRow[] {
  const groups = new Map<string, MappingRow>();
  for (const r of resources) {
    const key = `${r.canonical_type}::${r.target_service ?? ""}`;
    const existing = groups.get(key);
    if (existing) {
      existing.count += 1;
    } else {
      groups.set(key, { canonicalType: r.canonical_type, targetService: r.target_service, count: 1 });
    }
  }
  return [...groups.values()].sort((a, b) => b.count - a.count);
}

export function MappingTab({
  resources,
  isAnalyzeOnly,
}: {
  resources: ResourceAssessment[];
  isAnalyzeOnly: boolean;
}) {
  if (isAnalyzeOnly) {
    return (
      <EmptyState
        icon="🔍"
        message="Analyze-only mode has no target cloud — select an AWS→GCP or GCP→AWS use case to see resource mapping."
      />
    );
  }

  const rows = groupByMapping(resources);
  const totalInput = resources.length;
  const totalMapped = rows.filter((r) => r.targetService).reduce((sum, r) => sum + r.count, 0);

  const columns: DataTableColumn<MappingRow>[] = [
    {
      key: "source",
      header: "Source Type",
      render: (r) => (
        <span className="font-mono text-sm text-foreground/90">
          {r.canonicalType.split(".")[1] ?? r.canonicalType}
        </span>
      ),
    },
    {
      key: "count",
      header: "Count",
      align: "center",
      render: (r) => (
        <span className="font-mono font-semibold" style={{ color: COLORS.cyan }}>
          {r.count}
        </span>
      ),
    },
    {
      key: "arrow",
      header: "",
      align: "center",
      render: () => <span className="text-muted-foreground">→</span>,
    },
    {
      key: "target",
      header: "Target Service",
      render: (r) =>
        r.targetService ? (
          <span className="font-mono text-xs" style={{ color: COLORS.green }}>
            {r.targetService}
          </span>
        ) : (
          <span className="font-mono text-xs" style={{ color: COLORS.yellow }}>
            Manual migration required
          </span>
        ),
    },
  ];

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-3">
        <MetricCard label="Input Resources" value={totalInput} color={COLORS.cyan} />
        <MetricCard
          label="Mapped to Target"
          value={totalMapped}
          sub={`of ${totalInput} total`}
          color={totalMapped === totalInput ? COLORS.green : COLORS.yellow}
        />
      </div>
      <DataTable columns={columns} rows={rows} getRowKey={(r) => `${r.canonicalType}-${r.targetService ?? "none"}`} />
    </div>
  );
}
