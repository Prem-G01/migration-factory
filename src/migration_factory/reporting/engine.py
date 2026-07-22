"""Reporting Engine.

Consumes outputs from every engine (assessment, translation, security,
compliance, FinOps, validation, Terraform generation) and produces
structured reports in Markdown, JSON, and HTML.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from migration_factory.assessment.models import MigrationAssessment
from migration_factory.compliance.engine import ComplianceReport
from migration_factory.core.logging import get_logger
from migration_factory.domain.canonical_model import CanonicalInfrastructureGraph
from migration_factory.finops.engine import FinOpsReport
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
