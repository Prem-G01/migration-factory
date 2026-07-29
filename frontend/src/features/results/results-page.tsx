"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { Download, FileText, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { MetricCard } from "@/components/ui/metric-card";
import { EmptyState } from "@/components/ui/empty-state";
import { DisclosureNote } from "@/components/ui/disclosure-note";
import { DataTable, type DataTableColumn } from "@/components/data/data-table";
import { WaveTimeline } from "@/components/data/timeline";
import { ComplianceBarChart } from "@/components/data/charts";
import { ScoreRing } from "@/components/data/score-ring";
import { AIAnalysisPanel } from "@/features/results/ai-analysis-panel";
import { useReport } from "@/hooks/use-migration-queries";
import { useDownloadTerraform } from "@/hooks/use-migration-queries";
import { getHtmlReport } from "@/services/migration-api";
import { COLORS, RISK_COLORS, STRATEGY_COLORS, directionColor, scoreColor } from "@/constants/theme";
import type { ResourceAssessment, SecurityFinding } from "@/types/migration";
import { Skeleton } from "@/components/ui/skeleton";

function severityColor(severity: string): string {
  return severity === "high" || severity === "critical"
    ? COLORS.accentRed
    : COLORS.accentYellow;
}

export function ResultsPage({ runId }: { runId: string }) {
  const router = useRouter();
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
          <Button variant="outline" onClick={() => router.push("/")}>
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
      render: (r) => (
        <span className="font-mono text-xs text-foreground/90">{r.resource_name}</span>
      ),
    },
    {
      key: "type",
      header: "Type",
      render: (r) => (
        <span className="font-mono text-[11px] text-muted-foreground">
          {r.canonical_type.split(".")[1] ?? r.canonical_type}
        </span>
      ),
    },
    {
      key: "score",
      header: "Score",
      render: (r) => (
        <span
          className="font-mono font-semibold"
          style={{ color: scoreColor(r.complexity_score, true) }}
        >
          {r.complexity_score}
        </span>
      ),
    },
    {
      key: "strategy",
      header: "Strategy",
      render: (r) => (
        <span
          className="rounded-full px-2 py-0.5 font-mono text-[10px]"
          style={{
            color: STRATEGY_COLORS[r.strategy],
            background: `${STRATEGY_COLORS[r.strategy]}1a`,
          }}
        >
          {r.strategy}
        </span>
      ),
    },
    {
      key: "target",
      header: "Target",
      render: (r) => (
        <span className="font-mono text-[11px] text-muted-foreground">
          {r.target_service ?? "—"}
        </span>
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

  return (
    <div className="flex h-full flex-col gap-4 p-6">
      <div className="flex items-center justify-between">
        <span
          className="rounded-full border px-3 py-1 font-mono text-xs"
          style={{
            color: directionColor(report.direction),
            borderColor: `${directionColor(report.direction)}40`,
            background: `${directionColor(report.direction)}14`,
          }}
        >
          {report.direction}
        </span>
        <Button variant="outline" size="sm" onClick={() => router.push("/")}>
          + New Analysis
        </Button>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <MetricCard label="Complexity" value={s.complexity_score} sub="/ 100" color={scoreColor(s.complexity_score, true)} />
        <MetricCard label="Risk" value={s.risk_level.toUpperCase()} sub="level" color={RISK_COLORS[s.risk_level] ?? COLORS.textMuted} />
        <MetricCard label="Confidence" value={s.confidence_score} sub="/ 100" color={scoreColor(s.confidence_score)} />
        <MetricCard label="Security" value={s.security_score} sub="/ 100" color={scoreColor(s.security_score)} />
        <MetricCard label="Savings" value={s.monthly_savings} prefix="$" sub="/month (estimated)" color={COLORS.accentGreen} />
        <MetricCard
          label="Downtime"
          value={s.downtime_minutes}
          sub="minutes"
          color={s.downtime_minutes < 10 ? COLORS.accentGreen : s.downtime_minutes < 60 ? COLORS.accentYellow : COLORS.accentRed}
        />
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
              <span className="ml-1 rounded-full bg-[rgba(251,191,36,0.2)] px-1.5 py-px text-[9px] text-[#fbbf24]">
                {blockers.length}
              </span>
            )}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="waves">
          {report.plan.waves.length === 0 ? (
            <EmptyState
              icon="🌊"
              message='No waves — analysis-only mode. Select GCP or AWS target to get a migration plan.'
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
          <DisclosureNote>
            Checks are configuration-based against each framework&apos;s rules. For
            live compliance, use AWS Security Hub or GCP Security Command Center.
          </DisclosureNote>
          {frameworks.length > 0 && <ComplianceBarChart frameworks={frameworks} />}
          <div className="mt-3 flex flex-col gap-2">
            {frameworks.map((f) => (
              <div key={f.framework} className="flex items-center justify-between text-xs">
                <span className="font-mono text-muted-foreground">{f.framework}</span>
                <span className="font-mono text-muted-foreground">
                  {f.passed}/{f.total_checks} passed
                  {f.failed_check_ids.length > 0 && (
                    <span className="ml-2 text-destructive/80">
                      · {f.failed_check_ids.slice(0, 2).join(", ")}
                    </span>
                  )}
                </span>
              </div>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="security">
          <DisclosureNote>
            Analysis is based on infrastructure configuration. Runtime security
            requires AWS GuardDuty or GCP Security Command Center.
          </DisclosureNote>
          <div className="mb-4 flex items-center gap-4 rounded-lg border border-white/5 bg-white/[0.02] p-3">
            <ScoreRing score={s.security_score} />
            <div>
              <div className="text-sm text-foreground/90">Security Score</div>
              <div className="font-mono text-xs text-muted-foreground">
                {s.security_score >= 80 ? "Good posture" : "Needs attention"}
              </div>
            </div>
          </div>
          {secFindings.length === 0 ? (
            <EmptyState icon="🛡️" message="No security findings detected." />
          ) : (
            <div className="flex flex-col gap-1.5">
              {secFindings.slice(0, 8).map((f, i) => (
                <div
                  key={i}
                  className="flex items-center gap-2 rounded-lg border border-white/5 bg-white/[0.02] px-3 py-2 text-xs"
                >
                  <span
                    className="rounded-full px-2 py-0.5 font-mono text-[10px]"
                    style={{
                      color: severityColor(f.severity),
                      background: `${severityColor(f.severity)}1a`,
                    }}
                  >
                    {f.severity.toUpperCase()}
                  </span>
                  <span className="flex-1 text-muted-foreground">
                    {f.message.slice(0, 60)}
                  </span>
                  <span className="font-mono text-[10px] text-muted-foreground/60">
                    {f.category}
                  </span>
                </div>
              ))}
            </div>
          )}
        </TabsContent>

        <TabsContent value="blockers">
          {blockers.length === 0 ? (
            <EmptyState icon="✅" message="No blockers found. Infrastructure is ready to migrate." />
          ) : (
            <div className="flex flex-col gap-1.5">
              {blockers.map((b, i) => (
                <div
                  key={i}
                  className="rounded-lg border-l-2 border-[#fbbf24] bg-[rgba(251,191,36,0.05)] px-3 py-2 text-xs text-muted-foreground"
                >
                  ⚠ {b}
                </div>
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>

      <AIAnalysisPanel ai={report.ai_analysis} />

      <div className="flex gap-2">
        {!isAnalyzeOnly && (
          <Button
            variant="outline"
            onClick={handleDownload}
            disabled={downloadTerraform.isPending}
            className="flex-1 gap-1.5"
          >
            {downloadTerraform.isPending ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <Download className="size-3.5" />
            )}
            Terraform
          </Button>
        )}
        <Button
          variant="outline"
          onClick={handleViewReport}
          disabled={viewingReport}
          className="flex-1 gap-1.5"
        >
          {viewingReport ? <Loader2 className="size-3.5 animate-spin" /> : <FileText className="size-3.5" />}
          Report
        </Button>
      </div>
    </div>
  );
}
