import { useMemo, useState } from "react";
import { downloadTerraform } from "../api";

const RISK_COLORS = {
  low: "bg-green-100 text-green-800",
  medium: "bg-yellow-100 text-yellow-800",
  high: "bg-red-100 text-red-800",
  critical: "bg-red-200 text-red-900",
};

const STRATEGY_COLORS = {
  rehost: "bg-green-100 text-green-800",
  replatform: "bg-yellow-100 text-yellow-800",
  manual: "bg-orange-100 text-orange-800",
  unsupported: "bg-red-100 text-red-800",
};

const SEVERITY_STYLES = {
  critical: "bg-red-100 text-red-900",
  high: "bg-orange-100 text-orange-800",
  medium: "bg-yellow-100 text-yellow-800",
  low: "bg-gray-100 text-gray-700",
  info: "bg-gray-100 text-gray-700",
};

function scoreColor(score, { invert = false } = {}) {
  if (invert) {
    if (score <= 30) return "text-green-600";
    if (score <= 60) return "text-yellow-600";
    return "text-red-600";
  }
  if (score >= 70) return "text-green-600";
  if (score >= 40) return "text-yellow-600";
  return "text-red-600";
}

function complianceBarColor(score) {
  if (score >= 80) return "bg-green-500";
  if (score >= 60) return "bg-yellow-500";
  return "bg-red-500";
}

function formatHours(hours) {
  if (hours >= 1) return `${hours.toFixed(1)}h`;
  return `${Math.round(hours * 60)}m`;
}

function directionBadge(report) {
  if (report.mode === "analyze") {
    return { label: "Analysis Only", classes: "bg-gray-100 text-gray-700" };
  }
  if ((report.source_provider || "").toLowerCase() === "aws") {
    return { label: report.direction, classes: "bg-blue-100 text-blue-800" };
  }
  return { label: report.direction, classes: "bg-orange-100 text-orange-800" };
}

export default function ResultsDashboard({ report, runId, onNewAnalysis }) {
  const [sortDesc, setSortDesc] = useState(true);
  const [copied, setCopied] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState(null);

  const badge = directionBadge(report);
  const summary = report.summary;

  const targetServiceByResource = useMemo(() => {
    const map = {};
    (report.translation_results || []).forEach((result) => {
      map[result.resource_id] = result.target_service;
    });
    return map;
  }, [report.translation_results]);

  const sortedResources = useMemo(() => {
    const resources = [...(report.assessment?.resource_assessments || [])];
    resources.sort((a, b) => (sortDesc ? b.complexity_score - a.complexity_score : a.complexity_score - b.complexity_score));
    return resources;
  }, [report.assessment, sortDesc]);

  const securityFindings = useMemo(() => {
    const security = report.security || {};
    const iam = (security.iam_findings || []).map((f) => ({
      severity: f.severity,
      type: f.finding_type,
      resource: f.resource_name,
      finding: f.message,
    }));
    const firewall = (security.firewall_findings || []).map((f) => ({
      severity: f.severity,
      type: f.finding_type,
      resource: f.resource_name,
      finding: f.message,
    }));
    const secrets = (security.secret_findings || []).map((f) => ({
      severity: f.severity,
      type: "secret_exposure",
      resource: f.resource_name,
      finding: `Secret pattern matched at ${f.attribute_path}: ${f.pattern_matched}`,
    }));
    return [...iam, ...firewall, ...secrets];
  }, [report.security]);

  async function handleDownloadTerraform() {
    setDownloading(true);
    setDownloadError(null);
    try {
      const blob = await downloadTerraform(runId);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `migration-terraform-${runId.slice(0, 8)}.zip`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setDownloadError(err.response?.data?.detail || "Terraform download failed.");
    } finally {
      setDownloading(false);
    }
  }

  function handleViewFullReport() {
    window.open(`http://localhost:8000/api/v1/report/${runId}/html`, "_blank");
  }

  async function handleCopyRunId() {
    await navigator.clipboard.writeText(runId);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div className="mx-auto max-w-6xl px-4 py-10">
      {/* Top bar */}
      <div className="mb-8 flex items-center justify-between">
        <span className={`rounded-full px-4 py-1.5 text-sm font-semibold ${badge.classes}`}>{badge.label}</span>
        <button
          onClick={onNewAnalysis}
          className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
        >
          New Analysis
        </button>
      </div>

      {/* Summary cards */}
      <div className="mb-8 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
        <SummaryCard label="Complexity" value={`${summary.complexity_score}/100`} colorClass={scoreColor(summary.complexity_score, { invert: true })} />
        <SummaryCard
          label="Risk Level"
          value={summary.risk_level.toUpperCase()}
          pillClass={RISK_COLORS[summary.risk_level] || "bg-gray-100 text-gray-700"}
        />
        <SummaryCard label="Confidence" value={`${summary.confidence_score}/100`} colorClass={scoreColor(summary.confidence_score)} />
        <SummaryCard label="Security Score" value={`${summary.security_score}/100`} colorClass={scoreColor(summary.security_score)} />
        <SummaryCard
          label="Monthly Savings"
          value={`$${summary.monthly_savings.toLocaleString()}`}
          colorClass={summary.monthly_savings >= 0 ? "text-green-600" : "text-red-600"}
        />
        <SummaryCard label="Downtime" value={`${summary.downtime_minutes} min`} colorClass="text-gray-800" />
      </div>

      {/* Migration Waves */}
      {report.mode === "migrate" && report.plan?.waves?.length > 0 && (
        <Section title="Migration Waves">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-gray-200 text-gray-500">
                <th className="py-2 pr-4">Wave</th>
                <th className="py-2 pr-4">Name</th>
                <th className="py-2 pr-4">Resources</th>
                <th className="py-2 pr-4">Mode</th>
                <th className="py-2 pr-4">Duration</th>
              </tr>
            </thead>
            <tbody>
              {report.plan.waves.map((wave) => (
                <tr key={wave.wave_number} className="border-b border-gray-100">
                  <td className="py-2 pr-4 font-medium">{wave.wave_number}</td>
                  <td className="py-2 pr-4">{wave.name}</td>
                  <td className="py-2 pr-4">{wave.resource_ids.length}</td>
                  <td className="py-2 pr-4">
                    {wave.can_parallelize ? (
                      <span className="text-blue-600">⚡ Parallel</span>
                    ) : (
                      <span className="text-gray-500">→ Sequential</span>
                    )}
                  </td>
                  <td className="py-2 pr-4">{formatHours(wave.estimated_duration_hours)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>
      )}

      {/* Resource Assessment */}
      <Section title="Resource Assessment">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-gray-200 text-gray-500">
              <th className="py-2 pr-4">Resource</th>
              <th className="py-2 pr-4">Type</th>
              <th className="cursor-pointer select-none py-2 pr-4" onClick={() => setSortDesc((v) => !v)}>
                Score {sortDesc ? "↓" : "↑"}
              </th>
              <th className="py-2 pr-4">Strategy</th>
              <th className="py-2 pr-4">Target Service</th>
              <th className="py-2 pr-4">Downtime</th>
              <th className="py-2 pr-4">Blockers</th>
            </tr>
          </thead>
          <tbody>
            {sortedResources.map((resource) => (
              <tr key={resource.resource_id} className="border-b border-gray-100">
                <td className="py-2 pr-4">{resource.resource_name}</td>
                <td className="py-2 pr-4 text-gray-500">{resource.canonical_type}</td>
                <td className="py-2 pr-4 font-medium">{resource.complexity_score}</td>
                <td className="py-2 pr-4">
                  <span
                    className={`rounded-full px-2.5 py-1 text-xs font-medium ${
                      STRATEGY_COLORS[resource.strategy] || "bg-gray-100 text-gray-700"
                    }`}
                  >
                    {resource.strategy}
                  </span>
                </td>
                <td className="py-2 pr-4 text-gray-500">{targetServiceByResource[resource.resource_id] || "—"}</td>
                <td className="py-2 pr-4">{resource.downtime}</td>
                <td className="py-2 pr-4">{resource.blockers.length}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>

      {/* Compliance */}
      {report.compliance?.framework_results?.length > 0 && (
        <Section title="Compliance">
          <div className="space-y-4">
            {report.compliance.framework_results.map((framework) => (
              <div key={framework.framework}>
                <div className="mb-1 flex items-center justify-between text-sm">
                  <span className="font-medium text-gray-800">{framework.framework}</span>
                  <span className="text-gray-500">
                    {framework.compliance_score.toFixed(0)}% — {framework.compliance_score >= 80 ? "Pass" : "Fail"}
                  </span>
                </div>
                <div className="h-2 w-full rounded-full bg-gray-100">
                  <div
                    className={`h-2 rounded-full ${complianceBarColor(framework.compliance_score)}`}
                    style={{ width: `${Math.min(100, framework.compliance_score)}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* Security Findings */}
      {securityFindings.length > 0 && (
        <Section title="Security Findings">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-gray-200 text-gray-500">
                <th className="py-2 pr-4">Severity</th>
                <th className="py-2 pr-4">Type</th>
                <th className="py-2 pr-4">Resource</th>
                <th className="py-2 pr-4">Finding</th>
              </tr>
            </thead>
            <tbody>
              {securityFindings.map((finding, index) => (
                <tr key={index} className="border-b border-gray-100">
                  <td className="py-2 pr-4">
                    <span className={`rounded px-2 py-1 text-xs font-medium ${SEVERITY_STYLES[finding.severity] || "bg-gray-100 text-gray-700"}`}>
                      {finding.severity}
                    </span>
                  </td>
                  <td className="py-2 pr-4 text-gray-500">{finding.type}</td>
                  <td className="py-2 pr-4">{finding.resource}</td>
                  <td className="py-2 pr-4">{finding.finding}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>
      )}

      {/* Blockers */}
      {report.assessment?.blockers?.length > 0 && (
        <Section title="Blockers">
          <div className="rounded-lg border border-yellow-300 bg-yellow-50 p-4">
            <ul className="list-inside list-disc space-y-1 text-sm text-yellow-800">
              {report.assessment.blockers.map((blocker, index) => (
                <li key={index}>{blocker}</li>
              ))}
            </ul>
          </div>
        </Section>
      )}

      {/* Actions */}
      <div className="mt-8 flex flex-wrap gap-3">
        {report.terraform_available && (
          <button
            onClick={handleDownloadTerraform}
            disabled={downloading}
            className="rounded-lg bg-blue-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-blue-300"
          >
            {downloading ? "Downloading…" : "Download Terraform"}
          </button>
        )}
        <button
          onClick={handleViewFullReport}
          className="rounded-lg border border-gray-300 px-5 py-2.5 text-sm font-semibold text-gray-700 hover:bg-gray-50"
        >
          View Full Report
        </button>
        <button
          onClick={handleCopyRunId}
          className="rounded-lg border border-gray-300 px-5 py-2.5 text-sm font-semibold text-gray-700 hover:bg-gray-50"
        >
          {copied ? "Copied!" : "Copy Run ID"}
        </button>
      </div>
      {downloadError && <p className="mt-3 text-sm text-red-600">{downloadError}</p>}
    </div>
  );
}

function SummaryCard({ label, value, colorClass, pillClass }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <p className="mb-1 text-xs font-medium uppercase tracking-wide text-gray-400">{label}</p>
      {pillClass ? (
        <span className={`inline-block rounded-full px-2.5 py-1 text-sm font-bold ${pillClass}`}>{value}</span>
      ) : (
        <p className={`text-2xl font-bold ${colorClass}`}>{value}</p>
      )}
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div className="mb-8 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
      <h2 className="mb-4 text-lg font-semibold text-gray-900">{title}</h2>
      {children}
    </div>
  );
}
