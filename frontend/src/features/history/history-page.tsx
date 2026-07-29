"use client";

import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { DataTable, type DataTableColumn } from "@/components/data/data-table";
import { useDeleteRun, useRuns } from "@/hooks/use-migration-queries";
import { RISK_COLORS, directionColor } from "@/constants/theme";
import type { RunListItem } from "@/types/migration";

export function HistoryPage() {
  const router = useRouter();
  const { data, isLoading } = useRuns();
  const deleteRun = useDeleteRun();

  const runs = data?.runs ?? [];

  const handleDelete = async (runId: string) => {
    if (!confirm("Delete this run?")) return;
    try {
      await deleteRun.mutateAsync(runId);
      toast.success("Run deleted");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to delete run");
    }
  };

  const columns: DataTableColumn<RunListItem>[] = [
    {
      key: "direction",
      header: "Direction",
      render: (r) => (
        <span
          className="rounded-full px-2 py-0.5 font-mono text-[10px]"
          style={{
            color: directionColor(r.direction),
            background: `${directionColor(r.direction)}14`,
          }}
        >
          {r.direction || "Analysis"}
        </span>
      ),
    },
    {
      key: "resources",
      header: "Resources",
      align: "right",
      render: (r) => (
        <span className="font-mono text-muted-foreground">{r.resources ?? "—"}</span>
      ),
    },
    {
      key: "risk",
      header: "Risk",
      render: (r) =>
        r.risk_level ? (
          <span
            className="font-mono text-xs font-semibold"
            style={{ color: RISK_COLORS[r.risk_level] }}
          >
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
        <span className="font-mono text-[#34d399]">
          {r.monthly_savings != null ? `$${r.monthly_savings}/mo` : "—"}
        </span>
      ),
    },
    {
      key: "duration",
      header: "Duration",
      align: "right",
      render: (r) => (
        <span className="font-mono text-xs text-muted-foreground">
          {r.duration_seconds != null ? `${r.duration_seconds.toFixed(1)}s` : "—"}
        </span>
      ),
    },
    {
      key: "actions",
      header: "",
      align: "right",
      render: (r) => (
        <div className="flex justify-end gap-3">
          <button
            onClick={() => router.push(`/results?run=${r.run_id}`)}
            className="text-xs font-medium text-primary hover:opacity-80"
          >
            View
          </button>
          <button
            onClick={() => handleDelete(r.run_id)}
            className="text-muted-foreground hover:text-destructive"
            aria-label="Delete run"
          >
            <Trash2 className="size-3.5" />
          </button>
        </div>
      ),
    },
  ];

  return (
    <div className="flex flex-col gap-4 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold">Analysis History</h1>
          {!isLoading && (
            <span className="font-mono text-[11px] text-muted-foreground">
              {runs.length} run{runs.length === 1 ? "" : "s"}
            </span>
          )}
        </div>
        <Button variant="outline" onClick={() => router.push("/")}>
          + New Analysis
        </Button>
      </div>

      {isLoading ? (
        <div className="flex flex-col gap-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-10 rounded-lg" />
          ))}
        </div>
      ) : (
        <DataTable
          columns={columns}
          rows={runs}
          getRowKey={(r) => r.run_id}
          getRowAccent={(r) => directionColor(r.direction)}
          emptyState={
            <EmptyState
              icon="📋"
              message="No analyses yet. Upload a file to get started."
              action={
                <Button variant="outline" onClick={() => router.push("/")}>
                  New Analysis →
                </Button>
              }
            />
          }
        />
      )}
    </div>
  );
}
