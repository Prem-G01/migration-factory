"""Workflow Engine.

Configurable stage-based pipeline that orchestrates the full migration
lifecycle: discovery -> assessment -> validation -> security -> compliance ->
finops -> terraform -> deployment -> verification. Stages are composable,
reorderable, and can be skipped or added without modifying core code.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from migration_factory.core.logging import get_logger

logger = get_logger(__name__)


class StageStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class StageResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stage_name: str
    status: StageStatus
    duration_seconds: float = 0
    output: dict[str, Any] = Field(default_factory=dict)
    error: str = ""


class WorkflowDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    description: str = ""
    stages: list[str] = Field(default_factory=list)
    required_stages: list[str] = Field(default_factory=list)


class WorkflowReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workflow_name: str
    status: StageStatus
    stage_results: list[StageResult] = Field(default_factory=list)
    total_duration_seconds: float = 0

    @property
    def completed_stages(self) -> int:
        return sum(1 for s in self.stage_results if s.status is StageStatus.COMPLETED)

    @property
    def failed_stages(self) -> int:
        return sum(1 for s in self.stage_results if s.status is StageStatus.FAILED)


# Pre-defined workflows
DISCOVERY_WORKFLOW = WorkflowDefinition(
    name="discovery", description="Discover and inventory cloud infrastructure",
    stages=["cloud_discovery", "parse", "normalize", "enrich", "knowledge_graph"],
)

ASSESSMENT_WORKFLOW = WorkflowDefinition(
    name="assessment", description="Assess migration complexity and readiness",
    stages=["translate", "assess", "business_impact", "tech_debt", "readiness"],
)

MIGRATION_WORKFLOW = WorkflowDefinition(
    name="migration", description="Full migration pipeline",
    stages=["parse", "normalize", "enrich", "translate", "assess", "validate",
            "security", "compliance", "finops", "terraform_generate", "report"],
    required_stages=["parse", "normalize", "translate", "assess"],
)

VALIDATION_WORKFLOW = WorkflowDefinition(
    name="validation", description="Validate infrastructure and policies",
    stages=["validate", "security", "compliance", "policy"],
)

SECURITY_WORKFLOW = WorkflowDefinition(
    name="security", description="Security assessment pipeline",
    stages=["security", "compliance", "policy"],
)

TERRAFORM_WORKFLOW = WorkflowDefinition(
    name="terraform", description="Generate and deploy Terraform",
    stages=["terraform_generate", "terraform_validate", "terraform_plan", "terraform_apply"],
)

REPORTING_WORKFLOW = WorkflowDefinition(
    name="reporting", description="Generate all reports",
    stages=["report_migration", "report_security", "report_compliance", "report_finops", "report_inventory"],
)

PREDEFINED_WORKFLOWS: dict[str, WorkflowDefinition] = {
    w.name: w for w in [
        DISCOVERY_WORKFLOW, ASSESSMENT_WORKFLOW, MIGRATION_WORKFLOW,
        VALIDATION_WORKFLOW, SECURITY_WORKFLOW, TERRAFORM_WORKFLOW, REPORTING_WORKFLOW,
    ]
}


StageHandler = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(slots=True)
class WorkflowEngine:
    """Executes configurable workflows by dispatching to registered stage handlers."""

    _handlers: dict[str, StageHandler] = field(default_factory=dict)

    def register_stage(self, name: str, handler: StageHandler) -> None:
        self._handlers[name] = handler
        logger.debug("workflow_stage_registered", stage=name)

    def execute(
        self,
        workflow: WorkflowDefinition,
        context: dict[str, Any] | None = None,
        skip_stages: set[str] | None = None,
    ) -> WorkflowReport:
        ctx = context or {}
        skip = skip_stages or set()
        results: list[StageResult] = []
        overall_status = StageStatus.COMPLETED
        total_duration = 0.0

        logger.info("workflow_started", workflow=workflow.name, stages=len(workflow.stages))

        import time

        for stage_name in workflow.stages:
            if stage_name in skip:
                results.append(StageResult(stage_name=stage_name, status=StageStatus.SKIPPED))
                continue

            handler = self._handlers.get(stage_name)
            if handler is None:
                results.append(StageResult(
                    stage_name=stage_name, status=StageStatus.SKIPPED,
                    error=f"No handler registered for stage '{stage_name}'",
                ))
                continue

            start = time.monotonic()
            try:
                output = handler(ctx)
                ctx.update(output)
                duration = time.monotonic() - start
                total_duration += duration
                results.append(StageResult(
                    stage_name=stage_name, status=StageStatus.COMPLETED,
                    duration_seconds=round(duration, 3), output=output,
                ))
            except Exception as exc:
                duration = time.monotonic() - start
                total_duration += duration
                results.append(StageResult(
                    stage_name=stage_name, status=StageStatus.FAILED,
                    duration_seconds=round(duration, 3), error=str(exc),
                ))

                if stage_name in workflow.required_stages:
                    overall_status = StageStatus.FAILED
                    logger.error("workflow_required_stage_failed", stage=stage_name, error=str(exc))
                    break
                else:
                    logger.warning("workflow_optional_stage_failed", stage=stage_name, error=str(exc))

        report = WorkflowReport(
            workflow_name=workflow.name, status=overall_status,
            stage_results=results, total_duration_seconds=round(total_duration, 3),
        )

        logger.info("workflow_completed", workflow=workflow.name, status=overall_status.value,
                     completed=report.completed_stages, failed=report.failed_stages)
        return report


COMPLIANCE_WORKFLOW = WorkflowDefinition(
    name="compliance",
    description="Full compliance evaluation pipeline",
    stages=["parse", "normalize", "policy", "security", "compliance", "report_compliance"],
    required_stages=["policy", "compliance"],
)

PLUGIN_WORKFLOW = WorkflowDefinition(
    name="plugin",
    description="Plugin discovery, validation, and registration workflow",
    stages=["discover_parsers", "discover_mappers", "validate_plugins", "register_plugins"],
)

PREDEFINED_WORKFLOWS["compliance"] = COMPLIANCE_WORKFLOW
PREDEFINED_WORKFLOWS["plugin"] = PLUGIN_WORKFLOW
