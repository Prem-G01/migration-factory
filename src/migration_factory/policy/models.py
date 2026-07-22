"""Policy Engine.

The foundation that Security Engine, Compliance Engine, and organization-
specific rule packs all build on. A policy is a typed predicate evaluated
against a CanonicalResource (or the full graph); the engine runs all
applicable policies and returns structured results — pass, fail, warning,
or skip — with rationale on every finding.

Policies are loaded as data (JSON packs under `policy/data/` or org-
supplied external files), not hardcoded in Python. Adding a new rule is a
JSON edit, not a code change. The Python evaluator functions are registered
by `check_id` and dispatched by the engine — same plugin-like extensibility
pattern as parsers/mappers, but at the individual-check level.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from migration_factory.domain.canonical_model import (
    CanonicalInfrastructureGraph,
    CanonicalResource,
)


class PolicySeverity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class PolicyStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    WARNING = "warning"
    SKIP = "skip"


class PolicyDefinition(BaseModel):
    """A single policy rule definition — loaded from JSON data packs."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    check_id: str = Field(..., description="Stable, greppable identifier e.g. 'naming.resource_prefix'")
    name: str
    description: str
    severity: PolicySeverity
    category: str = Field(..., description="Grouping: naming, tags, encryption, iam, network, region, etc.")
    frameworks: list[str] = Field(
        default_factory=list,
        description="Compliance frameworks this rule contributes to: CIS, NIST, SOC2, PCI_DSS, ISO27001",
    )
    remediation: str = Field(default="", description="How to fix a violation")
    enabled: bool = True


class PolicyFinding(BaseModel):
    """Result of evaluating one policy against one resource."""

    model_config = ConfigDict(extra="forbid")

    check_id: str
    check_name: str
    resource_id: str
    resource_name: str
    status: PolicyStatus
    severity: PolicySeverity
    category: str
    message: str
    remediation: str = ""
    frameworks: list[str] = Field(default_factory=list)


class PolicyReport(BaseModel):
    """Aggregated findings from evaluating all policies against a graph."""

    model_config = ConfigDict(extra="forbid")

    findings: list[PolicyFinding] = Field(default_factory=list)

    @property
    def passed(self) -> list[PolicyFinding]:
        return [f for f in self.findings if f.status is PolicyStatus.PASS]

    @property
    def failed(self) -> list[PolicyFinding]:
        return [f for f in self.findings if f.status is PolicyStatus.FAIL]

    @property
    def warnings(self) -> list[PolicyFinding]:
        return [f for f in self.findings if f.status is PolicyStatus.WARNING]

    @property
    def summary(self) -> dict[str, int]:
        counts: dict[str, int] = {s.value: 0 for s in PolicyStatus}
        for f in self.findings:
            counts[f.status.value] += 1
        return counts

    def by_category(self) -> dict[str, list[PolicyFinding]]:
        result: dict[str, list[PolicyFinding]] = {}
        for f in self.findings:
            result.setdefault(f.category, []).append(f)
        return result

    def by_framework(self, framework: str) -> list[PolicyFinding]:
        return [f for f in self.findings if framework in f.frameworks]

    @property
    def compliance_score(self) -> float:
        """Percentage of evaluable checks that passed (excludes SKIPs)."""
        evaluable = [f for f in self.findings if f.status is not PolicyStatus.SKIP]
        if not evaluable:
            return 100.0
        passed = sum(1 for f in evaluable if f.status is PolicyStatus.PASS)
        return round(passed / len(evaluable) * 100, 1)


class BasePolicyCheck(ABC):
    """Interface for a single policy check implementation."""

    @abstractmethod
    def evaluate(
        self,
        resource: CanonicalResource,
        graph: CanonicalInfrastructureGraph,
        policy: PolicyDefinition,
        parameters: dict[str, Any],
    ) -> PolicyFinding:
        raise NotImplementedError
