"""Reporting Engine.

Consumes outputs from every engine (assessment, translation, security,
compliance, FinOps, validation, Terraform generation) and produces
structured reports in Markdown, JSON, and HTML.
"""

from __future__ import annotations

import html as _html
from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from migration_factory.assessment.models import MigrationAssessment
from migration_factory.compliance.engine import ComplianceReport
from migration_factory.core.logging import get_logger
from migration_factory.domain.canonical_model import CanonicalInfrastructureGraph
from migration_factory.finops.engine import FinOpsReport
from migration_factory.planner.engine import EnhancedMigrationPlan
from migration_factory.security.engine import SecurityReport
from migration_factory.terraform_gen.engine import TerraformGenerationReport
from migration_factory.translation.models import TranslationReport
from migration_factory.validation.engine import ValidationReport

logger = get_logger(__name__)


class ReportSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    content: str


class MigrationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = "Migration Report"
    generated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    sections: list[ReportSection] = Field(default_factory=list)

    def to_markdown(self) -> str:
        lines = [f"# {self.title}", f"\nGenerated: {self.generated_at}\n"]
        for section in self.sections:
            lines.append(f"\n## {section.title}\n")
            lines.append(section.content)
        return "\n".join(lines)

    def to_json(self) -> str:
        return self.model_dump_json(indent=2)


@dataclass(slots=True)
class ReportingEngine:
    """Generates consolidated migration reports from engine outputs."""

    def generate(
        self,
        *,
        assessment: MigrationAssessment | None = None,
        translation: TranslationReport | None = None,
        security: SecurityReport | None = None,
        compliance: ComplianceReport | None = None,
        finops: FinOpsReport | None = None,
        validation: ValidationReport | None = None,
        terraform: TerraformGenerationReport | None = None,
    ) -> MigrationReport:
        sections: list[ReportSection] = []

        sections.append(self._executive_summary(assessment, security, compliance, finops))

        if assessment:
            sections.append(self._assessment_section(assessment))
        if translation:
            sections.append(self._translation_section(translation))
        if security:
            sections.append(self._security_section(security))
        if compliance:
            sections.append(self._compliance_section(compliance))
        if finops:
            sections.append(self._finops_section(finops))
        if validation:
            sections.append(self._validation_section(validation))
        if terraform:
            sections.append(self._terraform_section(terraform))

        report = MigrationReport(sections=sections)

        logger.info(
            "report_generated",
            section_count=len(sections),
        )
        return report

    @staticmethod
    def _executive_summary(
        assessment: MigrationAssessment | None,
        security: SecurityReport | None,
        compliance: ComplianceReport | None,
        finops: FinOpsReport | None,
    ) -> ReportSection:
        lines: list[str] = []

        if assessment:
            lines.append(f"**Overall complexity**: {assessment.overall_complexity_score}/100")
            lines.append(f"**Risk level**: {assessment.risk_level.value}")
            lines.append(f"**Resources**: {len(assessment.resource_assessments)}")
            lines.append(f"**Blockers**: {len(assessment.blockers)}")
            lines.append(f"**Migration phases**: {len(assessment.phases)}")

        if security:
            lines.append(f"**Security score**: {security.security_score}/100")
            lines.append(f"**Security risk**: {security.risk_level.value}")

        if compliance:
            lines.append(f"**Compliance score**: {compliance.overall_compliance_score}%")

        if finops:
            s = finops.cost_summary
            lines.append(f"**Source monthly cost**: ${s.source_monthly_total:,.0f}")
            lines.append(f"**Target monthly cost**: ${s.target_monthly_total:,.0f}")
            lines.append(f"**Monthly savings**: ${s.monthly_savings:,.0f}")
            lines.append(f"**Break-even**: {s.break_even_months:.1f} months")

        if assessment and assessment.recommendation:
            lines.append(f"\n**Recommendation**: {assessment.recommendation}")

        return ReportSection(
            title="Executive summary",
            content="\n".join(lines) if lines else "No data available.",
        )

    @staticmethod
    def _assessment_section(assessment: MigrationAssessment) -> ReportSection:
        lines: list[str] = []
        lines.append(f"Overall complexity score: {assessment.overall_complexity_score}/100\n")

        lines.append("| Resource | Type | Score | Strategy | Downtime | Blockers |")
        lines.append("|----------|------|-------|----------|----------|----------|")
        for ra in assessment.resource_assessments:
            blockers = len(ra.blockers)
            lines.append(
                f"| {ra.resource_name} | {ra.canonical_type.value} | "
                f"{ra.complexity_score} | {ra.strategy.value} | "
                f"{ra.downtime.value} | {blockers} |"
            )

        if assessment.phases:
            lines.append("\n### Migration phases\n")
            for phase in assessment.phases:
                lines.append(f"**Phase {phase.phase_number}: {phase.name}** — {len(phase.resource_ids)} resources")

        return ReportSection(title="Migration assessment", content="\n".join(lines))

    @staticmethod
    def _translation_section(translation: TranslationReport) -> ReportSection:
        lines: list[str] = []
        lines.append(f"Source: {translation.source_provider.value} → Target: {translation.target_provider.value}\n")

        summary = translation.summary
        lines.append(f"Supported: {summary.get('supported', 0)} | "
                      f"Partial: {summary.get('partial', 0)} | "
                      f"Manual: {summary.get('manual', 0)} | "
                      f"Unsupported: {summary.get('unsupported', 0)}\n")

        lines.append("| Resource | Status | Target service | Required changes |")
        lines.append("|----------|--------|----------------|------------------|")
        for tr in translation.results:
            changes = len(tr.required_changes)
            lines.append(
                f"| {tr.resource_name} | {tr.status.value} | "
                f"{tr.target_service or 'N/A'} | {changes} |"
            )

        return ReportSection(title="Translation plan", content="\n".join(lines))

    @staticmethod
    def _security_section(security: SecurityReport) -> ReportSection:
        lines: list[str] = []
        lines.append(f"Security score: {security.security_score}/100")
        lines.append(f"Risk level: {security.risk_level.value}\n")

        if security.iam_findings:
            lines.append(f"### IAM findings ({len(security.iam_findings)})\n")
            for iam_f in security.iam_findings:
                lines.append(f"- [{iam_f.severity.value}] {iam_f.message}")

        if security.secret_findings:
            lines.append(f"\n### Secrets detected ({len(security.secret_findings)})\n")
            for sec_f in security.secret_findings:
                lines.append(f"- [CRITICAL] Potential secret in {sec_f.resource_name} at {sec_f.attribute_path}")

        if security.firewall_findings:
            lines.append(f"\n### Firewall findings ({len(security.firewall_findings)})\n")
            for fw_f in security.firewall_findings:
                lines.append(f"- [{fw_f.severity.value}] {fw_f.message}")

        return ReportSection(title="Security analysis", content="\n".join(lines))

    @staticmethod
    def _compliance_section(compliance: ComplianceReport) -> ReportSection:
        lines: list[str] = []
        lines.append(f"Overall compliance: {compliance.overall_compliance_score}%\n")

        lines.append("| Framework | Score | Passed | Failed | Status |")
        lines.append("|-----------|-------|--------|--------|--------|")
        for fr in compliance.framework_results:
            status = "Compliant" if fr.compliance_score >= 80 else "Non-compliant"
            lines.append(
                f"| {fr.framework} | {fr.compliance_score}% | "
                f"{fr.passed} | {fr.failed} | {status} |"
            )

        return ReportSection(title="Compliance assessment", content="\n".join(lines))

    @staticmethod
    def _finops_section(finops: FinOpsReport) -> ReportSection:
        s = finops.cost_summary
        lines: list[str] = []
        lines.append(f"Source monthly: ${s.source_monthly_total:,.2f}")
        lines.append(f"Target monthly: ${s.target_monthly_total:,.2f}")
        lines.append(f"Monthly savings: ${s.monthly_savings:,.2f} ({s.savings_percentage:.1f}%)")
        lines.append(f"Yearly savings: ${s.yearly_savings:,.2f}")
        lines.append(f"Migration cost: ${s.total_migration_cost:,.2f}")
        lines.append(f"Break-even: {s.break_even_months:.1f} months")
        lines.append(f"Idle resources: {s.idle_resource_count} (${s.idle_monthly_waste:,.2f}/month wasted)")

        if finops.savings_recommendations:
            lines.append("\n### Recommendations\n")
            for rec in finops.savings_recommendations:
                lines.append(f"- {rec}")

        return ReportSection(title="FinOps analysis", content="\n".join(lines))

    @staticmethod
    def _validation_section(validation: ValidationReport) -> ReportSection:
        lines: list[str] = []
        summary = validation.summary
        lines.append(f"Errors: {summary.get('error', 0)} | "
                      f"Warnings: {summary.get('warning', 0)} | "
                      f"Info: {summary.get('info', 0)}\n")

        if validation.errors:
            lines.append("### Errors\n")
            for f in validation.errors:
                lines.append(f"- [{f.check}] {f.resource_name}: {f.message}")

        if validation.warnings:
            lines.append("\n### Warnings\n")
            for f in validation.warnings:
                lines.append(f"- [{f.check}] {f.resource_name}: {f.message}")

        return ReportSection(title="Validation results", content="\n".join(lines))

    @staticmethod
    def _terraform_section(terraform: TerraformGenerationReport) -> ReportSection:
        lines: list[str] = []
        lines.append(f"Target: {terraform.target_provider.value}")
        lines.append(f"Generated resources: {terraform.generated_resources}")
        lines.append(f"Skipped resources: {terraform.skipped_resources}")
        lines.append(f"Files: {len(terraform.files)}\n")

        lines.append("| File | Description |")
        lines.append("|------|-------------|")
        for f in terraform.files:
            lines.append(f"| {f.filename} | {f.description} |")

        return ReportSection(title="Terraform generation", content="\n".join(lines))

    def generate_security_report(self, security: SecurityReport) -> MigrationReport:
        return MigrationReport(
            title="Security Assessment Report",
            sections=[self._executive_summary(None, security, None, None), self._security_section(security)],
        )

    def generate_compliance_report(self, compliance: ComplianceReport) -> MigrationReport:
        return MigrationReport(
            title="Compliance Assessment Report",
            sections=[self._executive_summary(None, None, compliance, None), self._compliance_section(compliance)],
        )

    def generate_finops_report(self, finops: FinOpsReport) -> MigrationReport:
        return MigrationReport(
            title="FinOps Analysis Report",
            sections=[self._executive_summary(None, None, None, finops), self._finops_section(finops)],
        )

    def generate_inventory_report(self, graph: CanonicalInfrastructureGraph) -> MigrationReport:
        lines = [f"Total resources: {len(graph.resources)}\n"]
        lines.append("| ID | Type | Provider | Region | Owner | Environment |")
        lines.append("|---|---|---|---|---|---|")
        for r in graph.resources.values():
            row = f"| {r.name} | {r.canonical_type.value} | {r.source_provider.value} |"
            lines.append(row)
        return MigrationReport(
            title="Infrastructure Inventory Report",
            sections=[ReportSection(title="Resource inventory", content="\n".join(lines))],
        )

    def generate_terraform_report(self, terraform: TerraformGenerationReport) -> MigrationReport:
        return MigrationReport(
            title="Terraform Generation Report",
            sections=[self._terraform_section(terraform)],
        )

    def to_html(self, report: MigrationReport) -> str:
        """Convert a MigrationReport to standalone HTML."""
        sections_html = ""
        for section in report.sections:
            # Basic markdown-to-html: headers, bold, tables
            content = section.content
            content = content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            # Convert markdown tables
            lines = content.split("\n")
            html_lines: list[str] = []
            in_table = False
            for line in lines:
                if line.startswith("|") and "|" in line[1:]:
                    if line.startswith("|---") or line.startswith("| ---"):
                        continue
                    cells = [c.strip() for c in line.split("|")[1:-1]]
                    if not in_table:
                        html_lines.append("<table><thead><tr>" + "".join(f"<th>{c}</th>" for c in cells) + "</tr></thead><tbody>")
                        in_table = True
                    else:
                        html_lines.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
                else:
                    if in_table:
                        html_lines.append("</tbody></table>")
                        in_table = False
                    if line.startswith("### "):
                        html_lines.append(f"<h4>{line[4:]}</h4>")
                    elif line.startswith("## "):
                        html_lines.append(f"<h3>{line[3:]}</h3>")
                    elif line.startswith("- "):
                        html_lines.append(f"<li>{line[2:]}</li>")
                    elif line.startswith("**") and line.endswith("**"):
                        html_lines.append(f"<p><strong>{line[2:-2]}</strong></p>")
                    else:
                        html_lines.append(f"<p>{line}</p>" if line.strip() else "")
            if in_table:
                html_lines.append("</tbody></table>")

            sections_html += f'<section><h2>{section.title}</h2>{"".join(html_lines)}</section>'

        return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>{report.title}</title>
<style>
body{{font-family:system-ui,sans-serif;max-width:900px;margin:2rem auto;padding:0 1rem;color:#1a1a1a}}
h1{{border-bottom:2px solid #2563eb;padding-bottom:0.5rem}}
h2{{color:#2563eb;border-bottom:1px solid #e5e7eb;padding-bottom:0.3rem}}
table{{border-collapse:collapse;width:100%;margin:1rem 0}}
th,td{{border:1px solid #d1d5db;padding:8px 12px;text-align:left}}
th{{background:#f3f4f6;font-weight:600}}
tr:nth-child(even){{background:#f9fafb}}
li{{margin:0.3rem 0}}
section{{margin:2rem 0}}
</style>
</head>
<body>
<h1>{report.title}</h1>
<p><em>Generated: {report.generated_at}</em></p>
{sections_html}
</body></html>"""

    def to_html_dashboard(
        self,
        *,
        assessment: MigrationAssessment | None = None,
        security: SecurityReport | None = None,
        compliance: ComplianceReport | None = None,
        finops: FinOpsReport | None = None,
        plan: EnhancedMigrationPlan | None = None,
        translation: TranslationReport | None = None,
        direction: str = "",
        version: str = "2.0.3",
    ) -> str:
        """Render the galaxy-themed dashboard report served at
        GET /api/v1/report/{run_id}/html and written to migration-report.html.

        Takes the raw per-engine outputs directly (the same objects already
        in scope at both call sites) rather than a MigrationReport, since a
        MigrationReport only carries pre-flattened markdown section text —
        it has no structured access to scores, waves, or resource rows.
        """
        esc = _html.escape

        complexity = assessment.overall_complexity_score if assessment else 0
        risk_val = assessment.risk_level.value if assessment else "unknown"
        blockers = assessment.blockers if assessment else []
        recommendation = assessment.recommendation if assessment else ""
        resources = assessment.resource_assessments if assessment else []

        sec_score = security.security_score if security else 0

        confidence = plan.confidence.overall_confidence if plan else 0
        downtime_minutes = plan.cutover_plan.total_downtime_minutes if plan else 0
        waves = plan.waves if plan else []

        s = finops.cost_summary if finops else None
        monthly_savings = s.monthly_savings if s else 0

        frameworks = compliance.framework_results if compliance else []

        # ResourceAssessment carries no target_service of its own — that
        # lives on the matching TranslationResult (same merge api/main.py
        # does for the JSON report, kept consistent here).
        target_by_resource: dict[str, str] = {}
        if translation:
            target_by_resource = {tr.resource_id: tr.target_service or "" for tr in translation.results}

        def score_color(value: int, invert: bool = False) -> str:
            if invert:
                return "#34d399" if value <= 30 else "#fbbf24" if value <= 60 else "#f87171"
            return "#34d399" if value >= 70 else "#fbbf24" if value >= 40 else "#f87171"

        risk_colors = {"low": "#34d399", "medium": "#fbbf24", "high": "#f87171", "critical": "#ef4444"}
        risk_color = risk_colors.get(risk_val.lower(), "#94a3b8")

        frameworks_html = ""
        for f in frameworks:
            pct = round(f.compliance_score)
            color = "#34d399" if pct >= 80 else "#fbbf24" if pct >= 60 else "#f87171"
            failed = ", ".join(esc(c) for c in f.failed_check_ids[:3])
            frameworks_html += f"""
        <div style="margin-bottom:16px">
          <div style="display:flex;justify-content:space-between;margin-bottom:6px">
            <span class="mono" style="font-size:13px;color:#94a3b8">{esc(f.framework)}</span>
            <span class="mono" style="font-size:13px;color:{color};font-weight:600">{pct}%</span>
          </div>
          <div style="height:4px;background:rgba(99,179,237,0.1);border-radius:2px">
            <div style="height:100%;width:{pct}%;background:{color};border-radius:2px"></div>
          </div>
          <div class="mono" style="font-size:11px;color:#4a6fa5;margin-top:4px">{('Failed: ' + failed) if failed else '✓ All checks passed'}</div>
        </div>"""
        if not frameworks_html:
            frameworks_html = '<div style="color:#4a6fa5;font-size:13px;padding:12px">No compliance data available.</div>'

        waves_html = ""
        for w in waves:
            dur = f"{int(w.estimated_duration_hours * 60)}m" if w.estimated_duration_hours < 1 else f"{w.estimated_duration_hours:.1f}h"
            badge_color = "#34d399" if w.can_parallelize else "#fbbf24"
            badge_text = "⚡ Parallel" if w.can_parallelize else "→ Sequential"
            waves_html += f"""
        <div style="display:flex;align-items:center;gap:12px;padding:10px 14px;background:rgba(10,20,50,0.5);border:1px solid rgba(99,179,237,0.08);border-radius:8px;margin-bottom:6px">
          <div style="width:24px;height:24px;border-radius:50%;background:rgba(59,130,246,0.12);border:1px solid rgba(59,130,246,0.25);display:flex;align-items:center;justify-content:center;font-size:11px;color:#60a5fa;flex-shrink:0" class="mono">{w.wave_number}</div>
          <div style="flex:1;font-size:13px;color:#94a3b8">{esc(w.name)} <span style="color:#4a6fa5;font-size:11px">({len(w.resource_ids)} resources)</span></div>
          <span class="mono" style="padding:2px 8px;border-radius:20px;font-size:11px;color:{badge_color};background:{badge_color}1a;border:1px solid {badge_color}33">{badge_text}</span>
          <span class="mono" style="font-size:11px;color:#4a6fa5">{dur}</span>
        </div>"""
        if not waves_html:
            waves_html = '<div style="color:#4a6fa5;font-size:13px;padding:12px">No migration waves (analyze-only mode).</div>'

        strat_colors = {"rehost": "#34d399", "replatform": "#fbbf24", "manual": "#fb923c"}
        resources_html = ""
        for r in resources[:20]:
            rtype_val = r.canonical_type.value
            score = r.complexity_score
            strat_val = r.strategy.value
            target = target_by_resource.get(r.resource_id) or "—"
            sc = score_color(score, invert=True)
            strat_color = strat_colors.get(strat_val, "#94a3b8")
            resources_html += f"""
        <tr>
          <td class="mono" style="padding:8px 12px;border-bottom:1px solid rgba(99,179,237,0.06);font-size:12px;color:#94a3b8">{esc(r.resource_name[:28])}</td>
          <td class="mono" style="padding:8px 12px;border-bottom:1px solid rgba(99,179,237,0.06);font-size:11px;color:#4a6fa5">{esc(rtype_val.split('.')[-1] if '.' in rtype_val else rtype_val)}</td>
          <td class="mono" style="padding:8px 12px;border-bottom:1px solid rgba(99,179,237,0.06);color:{sc};font-weight:600">{score}</td>
          <td style="padding:8px 12px;border-bottom:1px solid rgba(99,179,237,0.06)"><span class="mono" style="padding:2px 8px;border-radius:20px;font-size:11px;color:{strat_color};background:{strat_color}1a">{esc(strat_val)}</span></td>
          <td style="padding:8px 12px;border-bottom:1px solid rgba(99,179,237,0.06);font-size:11px;color:#4a6fa5">{esc(target[:24])}</td>
        </tr>"""
        if not resources_html:
            resources_html = '<tr><td colspan="5" style="padding:12px;color:#4a6fa5">No resources assessed.</td></tr>'

        blockers_html = "".join(
            f'<div style="padding:10px 14px;background:rgba(251,191,36,0.05);border:1px solid '
            f'rgba(251,191,36,0.15);border-left:3px solid #fbbf24;border-radius:6px;margin-bottom:6px;'
            f'font-size:13px;color:#94a3b8">⚠ {esc(b)}</div>'
            for b in blockers
        )
        if not blockers_html:
            blockers_html = '<div style="color:#34d399;font-size:13px;padding:12px">✓ No blockers — ready to migrate</div>'

        rec_html = (
            f'<div class="rec">{esc(recommendation)}</div>'
            if recommendation
            else '<div class="rec" style="color:#4a6fa5">No recommendation available.</div>'
        )

        generated_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Migration Factory Report</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:#020818;color:#e2e8f0;font-family:Inter,system-ui,sans-serif;font-size:14px;line-height:1.6;padding:32px;min-height:100vh}}
.mono{{font-family:'JetBrains Mono',monospace}}
.header{{display:flex;align-items:center;gap:16px;margin-bottom:32px;padding-bottom:20px;border-bottom:1px solid rgba(99,179,237,0.12)}}
.logo{{width:40px;height:40px;border-radius:10px;background:linear-gradient(135deg,#3b82f6,#06b6d4);display:flex;align-items:center;justify-content:center;font-size:20px}}
.title{{font-size:22px;font-weight:600;letter-spacing:-0.3px}}
.subtitle{{font-size:13px;color:#4a6fa5;margin-top:2px}}
.badge{{padding:3px 10px;border-radius:20px;font-size:11px}}
.metrics{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:28px}}
.metric{{background:rgba(10,20,50,0.6);border:1px solid rgba(99,179,237,0.1);border-radius:12px;padding:16px;position:relative;overflow:hidden}}
.metric::before{{content:'';position:absolute;top:0;left:0;right:0;height:2px;background:var(--accent)}}
.metric-label{{font-size:10px;color:#2d4a7a;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:6px}}
.metric-value{{font-size:26px;font-weight:600;line-height:1;color:var(--accent)}}
.metric-sub{{font-size:11px;color:#4a6fa5;margin-top:4px}}
.section{{margin-bottom:28px}}
.section-title{{font-size:11px;color:#2d4a7a;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:14px;padding-bottom:6px;border-bottom:1px solid rgba(99,179,237,0.08)}}
table{{width:100%;border-collapse:collapse}}
th{{font-size:10px;color:#2d4a7a;text-align:left;padding:8px 12px;border-bottom:1px solid rgba(99,179,237,0.1);text-transform:uppercase;letter-spacing:0.05em}}
.rec{{background:rgba(59,130,246,0.06);border:1px solid rgba(59,130,246,0.15);border-radius:10px;padding:16px;font-size:13px;color:#94a3b8;line-height:1.7}}
.footer{{margin-top:40px;padding-top:16px;border-top:1px solid rgba(99,179,237,0.08);font-size:11px;color:#2d4a7a;display:flex;justify-content:space-between}}
@media (max-width:640px){{.metrics{{grid-template-columns:repeat(2,1fr)}}}}
</style>
</head>
<body>
<div class="header">
  <div class="logo">\U0001f3ed</div>
  <div>
    <div class="title">Migration Factory</div>
    <div class="subtitle mono">{esc(direction) or 'AI-Powered Multi-Cloud Infrastructure Migration Report'}</div>
  </div>
  <div style="margin-left:auto;display:flex;gap:8px;align-items:center">
    <span class="badge mono" style="background:rgba(52,211,153,0.1);border:1px solid rgba(52,211,153,0.25);color:#34d399">v{esc(version)}</span>
    <span class="badge mono" style="background:{risk_color}1a;border:1px solid {risk_color}40;color:{risk_color}">{esc(risk_val.upper())}</span>
  </div>
</div>

<div class="metrics">
  <div class="metric" style="--accent:{score_color(complexity, invert=True)}">
    <div class="metric-label">Complexity</div>
    <div class="metric-value mono">{complexity}</div>
    <div class="metric-sub">/ 100</div>
  </div>
  <div class="metric" style="--accent:{risk_color}">
    <div class="metric-label">Risk Level</div>
    <div class="metric-value mono" style="font-size:20px">{esc(risk_val.upper())}</div>
    <div class="metric-sub">assessment</div>
  </div>
  <div class="metric" style="--accent:{score_color(confidence)}">
    <div class="metric-label">Confidence</div>
    <div class="metric-value mono">{confidence}</div>
    <div class="metric-sub">/ 100</div>
  </div>
  <div class="metric" style="--accent:{score_color(sec_score)}">
    <div class="metric-label">Security Score</div>
    <div class="metric-value mono">{sec_score}</div>
    <div class="metric-sub">/ 100</div>
  </div>
  <div class="metric" style="--accent:#34d399">
    <div class="metric-label">Monthly Savings</div>
    <div class="metric-value mono">${monthly_savings:,.0f}</div>
    <div class="metric-sub">/ month (estimated)</div>
    <div style="font-size:10px;color:#4a6fa5;margin-top:4px">
      * Estimated using on-demand pricing. Actual costs vary with reserved
      instances, committed use discounts, and data transfer.
    </div>
  </div>
  <div class="metric" style="--accent:{'#34d399' if downtime_minutes < 10 else '#fbbf24' if downtime_minutes < 60 else '#f87171'}">
    <div class="metric-label">Downtime</div>
    <div class="metric-value mono">{downtime_minutes}</div>
    <div class="metric-sub">minutes</div>
  </div>
</div>

<div class="section">
  <div class="section-title">Recommendation</div>
  {rec_html}
</div>

<div class="section">
  <div class="section-title">Migration Waves ({len(waves)})</div>
  {waves_html}
</div>

<div class="section">
  <div class="section-title">Resource Assessment ({len(resources)})</div>
  <table>
    <thead><tr><th>Resource</th><th>Type</th><th>Score</th><th>Strategy</th><th>Target</th></tr></thead>
    <tbody>{resources_html}</tbody>
  </table>
</div>

<div class="section">
  <div class="section-title">Compliance</div>
  {frameworks_html}
</div>

<div class="section">
  <div class="section-title">Blockers ({len(blockers)})</div>
  {blockers_html}
</div>

<div class="footer mono">
  <span>Migration Factory v{esc(version)}</span>
  <span>Generated {generated_at}</span>
</div>
</body>
</html>"""
