"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Download, FileText, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { MetricCard } from "@/components/ui/metric-card";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { DataTable, type DataTableColumn } from "@/components/data/data-table";
import { WaveTimeline } from "@/components/data/timeline";
import { ComplianceTab } from "@/features/results/compliance-tab";
import { SecurityTab } from "@/features/results/security-tab";
import { AITab } from "@/features/results/ai-tab";
import { useDownloadTerraform, useReport } from "@/hooks/use-migration-queries";
import { getHtmlReport } from "@/services/migration-api";
import { COLORS, RISK_COLORS, STRATEGY_COLORS, directionColor, scoreColor } from "@/constants/theme";
import type { ResourceAssessment, SecurityFinding } from "@/types/migration";

interface ResultsViewProps {
  runId: string;
  onNewAnalysis: () => void;
}

export function ResultsView({ runId, onNewAnalysis }: ResultsViewProps) {
  const { data: report, isLoading, isError, error } = useReport(runId);
  const downloadTerraform = useDownloadTerraform();
  const [viewingReport, setViewingReport] = useState(false);

  if (isLoading) {
    return (
      <div className="flex flex-col gap-4 p-6">
        <Skeleton className="h-8 w-48" />
        <div className="grid grid-cols-3 gap-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-24 rounded-xl" />
          ))}
        </div>
        <Skeleton className="h-64 rounded-xl" />
      </div>
    );
  }

  if (isError || !report) {
    return (
      <EmptyState
        icon="⚠️"
        message={error instanceof Error ? error.message : "Could not load this run."}
        action={
          <Button variant="outline" onClick={onNewAnalysis}>
            New analysis
          </Button>
        }
      />
    );
  }

  const s = report.summary;
  const isAnalyzeOnly = !report.terraform_available;
  const resources = report.assessment.resource_assessments;
  const blockers = report.assessment.blockers;
  const frameworks = report.compliance.framework_results;
  const secFindings: (SecurityFinding & { category: string })[] = [
    ...report.security.iam_findings.map((f) => ({ ...f, category: "IAM" })),
    ...report.security.firewall_findings.map((f) => ({ ...f, category: "Firewall" })),
    ...report.security.secret_findings.map((f) => ({ ...f, category: "Secrets" })),
  ];

  const resourceColumns: DataTableColumn<ResourceAssessment>[] = [
    {
      key: "name",
      header: "Resource",
      render: (r) => <span className="font-mono text-sm text-foreground/90">{r.resource_name}</span>,
    },
    {
      key: "type",
      header: "Type",
      render: (r) => (
        <span className="font-mono text-xs text-muted-foreground">
          {r.canonical_type.split(".")[1] ?? r.canonical_type}
        </span>
      ),
    },
    {
      key: "score",
      header: "Score",
      render: (r) => (
        <span className="font-mono font-semibold" style={{ color: scoreColor(r.complexity_score, true) }}>
          {r.complexity_score}
        </span>
      ),
    },
    {
      key: "strategy",
      header: "Strategy",
      render: (r) => (
        <span
          className="rounded-full px-2 py-0.5 font-mono text-[11px]"
          style={{ color: STRATEGY_COLORS[r.strategy], background: `${STRATEGY_COLORS[r.strategy]}1a` }}
        >
          {r.strategy}
        </span>
      ),
    },
    {
      key: "target",
      header: "Target",
      render: (r) => (
        <span className="font-mono text-xs text-muted-foreground">{r.target_service ?? "—"}</span>
      ),
    },
  ];

  const handleDownload = async () => {
    try {
      await downloadTerraform.mutateAsync(runId);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Download failed");
    }
  };

  const handleViewReport = async () => {
    setViewingReport(true);
    try {
      const html = await getHtmlReport(runId);
      const win = window.open();
      win?.document.write(html);
      win?.document.close();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not load report");
    } finally {
      setViewingReport(false);
    }
  };

  const dirColor = directionColor(report.direction);

  return (
    <div className="flex h-full flex-col">
    <div className="flex flex-1 flex-col gap-4 overflow-y-auto p-6 pb-4">
      <div className="animate-fade-up flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span
            className="rounded-full border px-3 py-1 font-mono text-sm"
            style={{ color: dirColor, borderColor: `${dirColor}40`, background: `${dirColor}14` }}
          >
            {report.direction}
          </span>
          <span className="font-mono text-xs text-muted-foreground">{runId.slice(0, 8)}</span>
        </div>
        <Button variant="outline" size="sm" onClick={onNewAnalysis}>
          New Analysis
        </Button>
      </div>

      <div className="grid grid-cols-3 gap-3">
        {[
          { label: "Complexity", value: s.complexity_score, sub: "/ 100", color: scoreColor(s.complexity_score, true) },
          { label: "Risk", value: s.risk_level.toUpperCase(), sub: "level", color: RISK_COLORS[s.risk_level] ?? COLORS.muted },
          { label: "Confidence", value: s.confidence_score, sub: "/ 100", color: scoreColor(s.confidence_score) },
          { label: "Security", value: s.security_score, sub: "/ 100", color: scoreColor(s.security_score) },
          { label: "Savings", value: s.monthly_savings, prefix: "$", sub: "/month (estimated)", color: COLORS.green },
          {
            label: "Downtime",
            value: s.downtime_minutes,
            sub: "minutes",
            color: s.downtime_minutes < 10 ? COLORS.green : s.downtime_minutes < 60 ? COLORS.yellow : COLORS.red,
          },
        ].map((m, i) => (
          <div key={m.label} className="animate-fade-up opacity-0" style={{ animationDelay: `${i * 50}ms` }}>
            <MetricCard label={m.label} value={m.value} prefix={m.prefix} sub={m.sub} color={m.color} />
          </div>
        ))}
      </div>

      <Tabs defaultValue="waves" className="flex-1">
        <TabsList>
          <TabsTrigger value="waves">Waves</TabsTrigger>
          <TabsTrigger value="resources">Resources</TabsTrigger>
          <TabsTrigger value="compliance">Compliance</TabsTrigger>
          <TabsTrigger value="security">Security</TabsTrigger>
          <TabsTrigger value="blockers">
            Blockers
            {blockers.length > 0 && (
              <span className="ml-1 rounded-full bg-[rgba(245,158,11,0.2)] px-1.5 py-px text-[10px] text-[var(--yellow)]">
                {blockers.length}
              </span>
            )}
          </TabsTrigger>
          <TabsTrigger value="ai">AI</TabsTrigger>
        </TabsList>

        <TabsContent value="waves">
          {report.plan.waves.length === 0 ? (
            <EmptyState
              icon="🌊"
              message="No waves — analysis-only mode. Select an AWS→GCP or GCP→AWS use case to get a migration plan."
            />
          ) : (
            <WaveTimeline waves={report.plan.waves} />
          )}
        </TabsContent>

        <TabsContent value="resources">
          <DataTable
            columns={resourceColumns}
            rows={resources}
            getRowKey={(r) => r.resource_id}
            getRowAccent={(r) => STRATEGY_COLORS[r.strategy]}
          />
        </TabsContent>

        <TabsContent value="compliance">
          <ComplianceTab frameworks={frameworks} />
        </TabsContent>

        <TabsContent value="security">
          <SecurityTab score={s.security_score} findings={secFindings} />
        </TabsContent>

        <TabsContent value="blockers">
          {blockers.length === 0 ? (
            <EmptyState icon="✅" message="No blockers found. Infrastructure is ready to migrate." />
          ) : (
            <div className="flex flex-col gap-2">
              {blockers.map((b, i) => (
                <div
                  key={i}
                  className="rounded-lg border-l-2 border-[var(--yellow)] bg-[rgba(245,158,11,0.05)] px-3 py-2.5 text-sm text-muted-foreground"
                >
                  ⚠ {b}
                </div>
              ))}
            </div>
          )}
        </TabsContent>

        <TabsContent value="ai">
          <AITab ai={report.ai_analysis} />
        </TabsContent>
      </Tabs>
    </div>

      <div className="flex shrink-0 justify-center gap-2 border-t border-white/5 bg-black/20 px-6 py-3 backdrop-blur-md">
        {!isAnalyzeOnly && (
          <Button
            onClick={handleDownload}
            disabled={downloadTerraform.isPending}
            className="animate-glow flex-1 gap-1.5 bg-gradient-to-r from-[var(--cyan)] to-[#0066ff] text-black"
          >
            {downloadTerraform.isPending ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Download className="size-4" />
            )}
            Download Terraform
          </Button>
        )}
        <Button
          variant="outline"
          onClick={handleViewReport}
          disabled={viewingReport}
          className="flex-1 gap-1.5"
        >
          {viewingReport ? <Loader2 className="size-4 animate-spin" /> : <FileText className="size-4" />}
          View Report
        </Button>
      </div>
    </div>
  );
}
