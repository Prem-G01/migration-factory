"""Compliance Engine.

Not a separate rule engine — compliance frameworks are a LENS on the Policy
Engine's findings. Every PolicyDefinition carries `frameworks: ["CIS", "NIST",
...]` tags. The Compliance Engine runs the Policy Engine, then slices the
results per framework, computes per-framework scores, and generates a
structured compliance report.

This avoids duplicating rules across frameworks (a single encryption check
contributes to CIS, NIST, SOC2, PCI_DSS, ISO27001, and HIPAA simultaneously)
while still producing the per-framework reports auditors expect.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict, Field

from migration_factory.core.logging import get_logger
from migration_factory.domain.canonical_model import CanonicalInfrastructureGraph
from migration_factory.policy.engine import PolicyEngine
from migration_factory.policy.models import PolicyReport, PolicyStatus

logger = get_logger(__name__)

SUPPORTED_FRAMEWORKS = ["CIS", "NIST", "SOC2", "PCI_DSS", "ISO27001", "HIPAA"]


class FrameworkResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    framework: str
    total_checks: int
    passed: int
    failed: int
    warnings: int
    skipped: int
    compliance_score: float = Field(..., ge=0, le=100)
    failed_check_ids: list[str] = Field(default_factory=list)


class ComplianceReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overall_compliance_score: float = Field(..., ge=0, le=100)
    framework_results: list[FrameworkResult] = Field(default_factory=list)
    policy_report: PolicyReport
    compliant_frameworks: list[str] = Field(default_factory=list)
    non_compliant_frameworks: list[str] = Field(default_factory=list)

    @property
    def summary(self) -> dict[str, float]:
        return {fr.framework: fr.compliance_score for fr in self.framework_results}


@dataclass(slots=True)
class ComplianceEngine:
    policy_engine: PolicyEngine = field(default_factory=PolicyEngine)
    frameworks: list[str] = field(default_factory=lambda: list(SUPPORTED_FRAMEWORKS))
    compliance_threshold: float = 80.0

    def evaluate(self, graph: CanonicalInfrastructureGraph) -> ComplianceReport:
        policy_report = self.policy_engine.evaluate(graph)

        framework_results: list[FrameworkResult] = []

        for framework in self.frameworks:
            findings = policy_report.by_framework(framework)
            if not findings:
                framework_results.append(FrameworkResult(
                    framework=framework,
                    total_checks=0,
                    passed=0,
                    failed=0,
                    warnings=0,
                    skipped=0,
                    compliance_score=100.0,
                    failed_check_ids=[],
                ))
                continue

            passed = sum(1 for f in findings if f.status is PolicyStatus.PASS)
            failed = sum(1 for f in findings if f.status is PolicyStatus.FAIL)
            warnings = sum(1 for f in findings if f.status is PolicyStatus.WARNING)
            skipped = sum(1 for f in findings if f.status is PolicyStatus.SKIP)
            evaluable = passed + failed + warnings
            score = round(passed / evaluable * 100, 1) if evaluable > 0 else 100.0

            failed_ids = sorted({f.check_id for f in findings if f.status is PolicyStatus.FAIL})

            framework_results.append(FrameworkResult(
                framework=framework,
                total_checks=len(findings),
                passed=passed,
                failed=failed,
                warnings=warnings,
                skipped=skipped,
                compliance_score=score,
                failed_check_ids=failed_ids,
            ))

        # Overall = weighted average (by check count)
        total_evaluable = sum(
            fr.passed + fr.failed + fr.warnings
            for fr in framework_results
        )
        total_passed = sum(fr.passed for fr in framework_results)
        overall_score = round(total_passed / total_evaluable * 100, 1) if total_evaluable > 0 else 100.0

        compliant = [fr.framework for fr in framework_results if fr.compliance_score >= self.compliance_threshold]
        non_compliant = [fr.framework for fr in framework_results if fr.compliance_score < self.compliance_threshold]

        report = ComplianceReport(
            overall_compliance_score=overall_score,
            framework_results=framework_results,
            policy_report=policy_report,
            compliant_frameworks=compliant,
            non_compliant_frameworks=non_compliant,
        )

        logger.info(
            "compliance_evaluation_completed",
            overall_score=overall_score,
            compliant_count=len(compliant),
            non_compliant_count=len(non_compliant),
        )
        return report
