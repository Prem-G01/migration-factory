"""CLI entrypoint.

Commands:
    migration-factory ingest <file>          -- parse + normalize only
    migration-factory poc <file>             -- full AWS<->GCP POC pipeline
    migration-factory poc <file> --target gcp|aws  -- choose target cloud
    migration-factory poc <file> --output ./out    -- write all artifacts
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from rich.console import Console

from migration_factory.core.config import Settings, get_settings
from migration_factory.core.exceptions import MigrationFactoryError
from migration_factory.core.logging import configure_logging, get_logger
from migration_factory.pipeline import IngestionPipeline

logger = get_logger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="migration-factory",
        description="AI-Powered Multi-Cloud Infrastructure Migration Factory",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # ── ingest ──────────────────────────────────────────────────────────────
    ingest = subparsers.add_parser("ingest", help="Parse + normalize a single input file")
    ingest.add_argument("source_path", type=Path)
    ingest.add_argument("--output", type=Path, default=None)

    # ── poc ─────────────────────────────────────────────────────────────────
    poc = subparsers.add_parser(
        "poc",
        help="Full AWS↔GCP migration POC — parse, translate, assess, secure, cost, plan, generate",
    )
    poc.add_argument("source_path", type=Path, help="Terraform state file (.tfstate)")
    poc.add_argument(
        "--target",
        choices=["gcp", "aws"],
        default="gcp",
        help="Target cloud provider (default: gcp)",
    )
    poc.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Directory to write Terraform output, reports, and artifacts",
    )
    poc.add_argument(
        "--no-color",
        action="store_true",
        help="Disable rich terminal colors",
    )
    poc.add_argument(
        "--mode",
        choices=["analyze", "migrate"],
        default="migrate",
        help=(
            "analyze: assessment, security, compliance, cost only — no Terraform output. "
            "migrate: full pipeline including Terraform generation (default)."
        ),
    )
    poc.add_argument(
        "--analyze-only",
        action="store_true",
        help="Shorthand for --mode analyze (assessment/security/compliance/cost, no Terraform output).",
    )

    # ── workflow ────────────────────────────────────────────────────────────
    workflow = subparsers.add_parser("workflow", help="Run a predefined workflow (see workflow/engine.py)")
    workflow.add_argument(
        "name",
        choices=["discovery", "assessment", "migration", "validation", "security",
                 "compliance", "terraform", "reporting", "plugin"],
    )
    workflow.add_argument("source_path", type=Path)
    workflow.add_argument("--target", choices=["gcp", "aws"], default="gcp")
    workflow.add_argument("--output", type=Path, default=None)

    return parser


def main(argv: list[str] | None = None) -> int:
    settings = get_settings()
    configure_logging(settings)
    args = _build_parser().parse_args(argv)

    if args.command == "ingest":
        return _run_ingest(args, settings)

    if args.command == "poc":
        return _run_poc(args, settings)

    if args.command == "workflow":
        return _run_workflow(args, settings)

    return 1


# ── ingest ───────────────────────────────────────────────────────────────────

def _run_ingest(args: argparse.Namespace, settings: Settings) -> int:
    pipeline = IngestionPipeline(settings=settings)
    try:
        report = pipeline.run(args.source_path)
    except MigrationFactoryError as exc:
        logger.error("ingestion_failed", **exc.to_dict())
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    output_json = report.model_dump_json(indent=2)
    if args.output:
        args.output.write_text(output_json, encoding="utf-8")
        print(f"Report written to {args.output}")
    else:
        print(output_json)

    if not report.is_clean:
        print(
            f"Completed with findings: "
            f"{len(report.parse_warnings)} parse warnings, "
            f"{len(report.unsupported_resources)} unsupported resources, "
            f"{len(report.dangling_dependencies)} dangling dependencies.",
            file=sys.stderr,
        )
    return 0


# ── workflow ─────────────────────────────────────────────────────────────────
#
# WorkflowEngine ships with zero registered stage handlers -- PREDEFINED_WORKFLOWS
# is just a catalog of stage *names* per workflow. These handlers thread a shared
# context dict through the real engines so `migration-factory workflow <name>`
# actually does something, rather than reporting every stage "skipped: no
# handler registered". Coverage is intentionally partial: cloud_discovery,
# terraform_validate/plan/apply, business_impact/tech_debt/readiness, the
# granular report_* variants, and the plugin-introspection stages have no
# handler here (see the printed per-stage status for what ran vs. was skipped).
# terraform_apply in particular is deliberately never wired to a real
# `terraform apply` -- this tool generates Terraform for a human to review,
# it does not auto-deploy.


def _wf_parse(ctx: dict[str, Any]) -> dict[str, Any]:
    from migration_factory.pipeline import IngestionPipeline

    ingestion = IngestionPipeline(settings=get_settings()).run(ctx["source_path"])
    return {"ingestion": ingestion, "graph": ingestion.graph}


def _wf_normalize(ctx: dict[str, Any]) -> dict[str, Any]:
    # Parsing (above) already maps ParsedResource -> CanonicalResource in one
    # call -- normalization has already happened by the time this stage runs.
    return {}


def _wf_enrich(ctx: dict[str, Any]) -> dict[str, Any]:
    from migration_factory.discovery.engine import DiscoveryEngine

    DiscoveryEngine().enrich(ctx["graph"])
    return {}


def _wf_knowledge_graph(ctx: dict[str, Any]) -> dict[str, Any]:
    from migration_factory.knowledge_graph.engine import KnowledgeGraphEngine

    return {"knowledge_graph": KnowledgeGraphEngine().analyze(ctx["graph"])}


def _wf_translate(ctx: dict[str, Any]) -> dict[str, Any]:
    from collections import Counter

    from migration_factory.domain.enums import CloudProvider
    from migration_factory.translation.engine import TranslationEngine
    from migration_factory.translation.matrix import load_builtin_matrix

    graph = ctx["graph"]
    provider_counts = Counter(r.source_provider.value for r in graph.resources.values())
    source_provider = CloudProvider(provider_counts.most_common(1)[0][0]) if provider_counts else CloudProvider.AWS
    target_provider = ctx.get("target_provider", CloudProvider.GCP)

    if source_provider is target_provider:
        translation = TranslationEngine.build_identity_report(graph, source_provider)
    else:
        matrix = load_builtin_matrix(source_provider, target_provider)
        translation = TranslationEngine(matrix=matrix).translate(graph)
    return {"translation": translation, "source_provider": source_provider, "target_provider": target_provider}


def _wf_assess(ctx: dict[str, Any]) -> dict[str, Any]:
    from migration_factory.assessment.engine import AssessmentEngine

    return {"assessment": AssessmentEngine().assess(ctx["graph"], ctx["translation"])}


def _wf_validate(ctx: dict[str, Any]) -> dict[str, Any]:
    from migration_factory.validation.engine import ValidationEngine

    return {"validation": ValidationEngine().validate(ctx["graph"])}


def _wf_security(ctx: dict[str, Any]) -> dict[str, Any]:
    from migration_factory.security.engine import SecurityEngine

    return {"security": SecurityEngine().analyze(ctx["graph"])}


def _wf_compliance(ctx: dict[str, Any]) -> dict[str, Any]:
    from migration_factory.compliance.engine import ComplianceEngine

    return {"compliance": ComplianceEngine().evaluate(ctx["graph"])}


def _wf_policy(ctx: dict[str, Any]) -> dict[str, Any]:
    from migration_factory.policy.engine import PolicyEngine

    return {"policy": PolicyEngine().evaluate(ctx["graph"])}


def _wf_finops(ctx: dict[str, Any]) -> dict[str, Any]:
    from migration_factory.finops.engine import FinOpsEngine

    return {"finops": FinOpsEngine(target_provider=ctx["target_provider"]).analyze(ctx["graph"])}


def _wf_terraform_generate(ctx: dict[str, Any]) -> dict[str, Any]:
    from migration_factory.terraform_gen.engine import TerraformGenerator

    # The "terraform" workflow runs terraform_generate with no prior
    # "translate" stage -- compute it here if a standalone run didn't
    # already populate it, instead of crashing on a missing key.
    extra: dict[str, Any] = {}
    translation = ctx.get("translation")
    if translation is None:
        extra = _wf_translate(ctx)
        translation = extra["translation"]

    gen = TerraformGenerator(target_provider=ctx["target_provider"], project_id="workflow-run")
    report = gen.generate(ctx["graph"], translation)
    output_dir = ctx.get("output")
    if output_dir:
        gen.write(report, output_dir / "terraform")
    return {**extra, "terraform": report}


def _wf_report(ctx: dict[str, Any]) -> dict[str, Any]:
    from migration_factory.reporting.engine import ReportingEngine

    report = ReportingEngine().generate(
        assessment=ctx.get("assessment"),
        translation=ctx.get("translation"),
        security=ctx.get("security"),
        compliance=ctx.get("compliance"),
        finops=ctx.get("finops"),
        validation=ctx.get("validation"),
        terraform=ctx.get("terraform"),
    )
    return {"report": report}


_WORKFLOW_HANDLERS: dict[str, Any] = {
    "parse": _wf_parse,
    "normalize": _wf_normalize,
    "enrich": _wf_enrich,
    "knowledge_graph": _wf_knowledge_graph,
    "translate": _wf_translate,
    "assess": _wf_assess,
    "validate": _wf_validate,
    "security": _wf_security,
    "compliance": _wf_compliance,
    "policy": _wf_policy,
    "finops": _wf_finops,
    "terraform_generate": _wf_terraform_generate,
    "report": _wf_report,
}


def _run_workflow(args: argparse.Namespace, settings: Settings) -> int:
    from migration_factory.domain.enums import CloudProvider
    from migration_factory.pipeline import IngestionPipeline
    from migration_factory.workflow.engine import PREDEFINED_WORKFLOWS, WorkflowEngine

    workflow_def = PREDEFINED_WORKFLOWS[args.name]
    print(f"Running workflow: {args.name}")
    print(f"Steps: {workflow_def.stages}")

    try:
        ingestion = IngestionPipeline(settings=settings).run(args.source_path)
    except MigrationFactoryError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    context: dict[str, Any] = {
        "source_path": args.source_path,
        "target": args.target,
        "output": args.output,
        "ingestion": ingestion,
        "graph": ingestion.graph,
        "target_provider": CloudProvider.GCP if args.target == "gcp" else CloudProvider.AWS,
    }

    engine = WorkflowEngine()
    for stage_name, handler in _WORKFLOW_HANDLERS.items():
        engine.register_stage(stage_name, handler)

    result = engine.execute(workflow_def, context=context)

    print(f"\nWorkflow '{result.workflow_name}': {result.status.value}")
    print(f"Completed: {result.completed_stages}  Failed: {result.failed_stages}  Total: {len(result.stage_results)}")
    for sr in result.stage_results:
        icon = {"completed": "✓", "failed": "✗", "skipped": "○"}.get(sr.status.value, "?")
        note = f" — {sr.error}" if sr.error else ""
        print(f"  {icon} {sr.stage_name} ({sr.duration_seconds}s){note}")

    return 0 if result.status.value != "failed" else 1


# ── poc ──────────────────────────────────────────────────────────────────────

def _run_poc(args: argparse.Namespace, settings: object) -> int:  # noqa: ANN001
    from rich import box
    from rich.console import Console
    from rich.panel import Panel

    console = Console(no_color=getattr(args, "no_color", False))
    mode = "analyze" if args.analyze_only else args.mode

    # ── Banner ────────────────────────────────────────────────────────────
    console.print()
    target_line = (
        "[dim]Mode:[/dim] [bold]ANALYZE ONLY[/bold]"
        if mode != "migrate"
        else f"[dim]Target:[/dim] [bold]{args.target.upper()}[/bold]"
    )
    console.print(Panel.fit(
        "[bold cyan]Migration Factory[/bold cyan]  [dim]AI-Powered Multi-Cloud Infrastructure Migration[/dim]\n"
        f"[dim]Source:[/dim] {args.source_path}   "
        f"{target_line}",
        border_style="cyan",
    ))
    console.print()

    source_path = args.source_path
    target_cloud = args.target
    output_dir = args.output

    try:
        _poc_pipeline(console, source_path, target_cloud, output_dir, box, mode=mode)
    except MigrationFactoryError as exc:
        console.print(f"\n[bold red]ERROR:[/bold red] {exc}")
        return 1
    except Exception as exc:
        console.print(f"\n[bold red]UNEXPECTED ERROR:[/bold red] {exc}")
        raise

    return 0


def _poc_pipeline(
    console: Console,
    source_path: Path,
    target_cloud: str,
    output_dir: Path | None,
    box: object,
    mode: str = "migrate",
) -> None:
    import time
    from collections import Counter

    from rich import box as rich_box
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
    from rich.table import Table

    from migration_factory.assessment.engine import AssessmentEngine
    from migration_factory.assessment.extended import (
        BusinessImpactAnalyzer,
        ReadinessAssessor,
        TechnicalDebtAnalyzer,
        generate_mermaid_diagram,
    )
    from migration_factory.compliance.engine import ComplianceEngine
    from migration_factory.core.config import get_settings
    from migration_factory.discovery.engine import DiscoveryEngine
    from migration_factory.domain.enums import CloudProvider
    from migration_factory.drift.engine import DriftDetectionEngine
    from migration_factory.events.engine import Event, EventBus, EventType, NotificationChannel, NotificationEngine
    from migration_factory.finops.engine import FinOpsEngine
    from migration_factory.knowledge_graph.engine import KnowledgeGraphEngine
    from migration_factory.metrics.collector import MetricsCollector
    from migration_factory.pipeline import IngestionPipeline
    from migration_factory.planner.engine import MigrationPlanner
    from migration_factory.policy.engine import PolicyEngine
    from migration_factory.reporting.engine import ReportingEngine
    from migration_factory.rollback.engine import RollbackPlanner
    from migration_factory.security.engine import SecurityEngine
    from migration_factory.terraform_gen.engine import TerraformGenerator
    from migration_factory.translation.engine import TranslationEngine
    from migration_factory.translation.matrix import load_builtin_matrix
    from migration_factory.validation.engine import ValidationEngine

    # Refined to the actual detected source once ingestion completes, below;
    # this default only matters if the source file yields zero resources.
    source_provider = CloudProvider.AWS
    target_provider = CloudProvider.GCP if target_cloud == "gcp" else CloudProvider.AWS

    metrics = MetricsCollector()
    pipeline_start = time.perf_counter()

    event_bus = EventBus()
    notifier = NotificationEngine()
    event_bus.subscribe(
        EventType.PIPELINE_COMPLETED,
        lambda e: notifier.notify(
            NotificationChannel.LOG,
            subject="Migration Factory: pipeline completed",
            body=f"{e.data.get('direction')}: {e.data.get('total_resources')} resources, "
            f"${e.data.get('savings')}/mo savings",
        ),
    )

    stages = [
        ("📥  Parsing infrastructure",        "Ingestion"),
        ("🔍  Enriching metadata",            "Discovery"),
        ("🗺️   Building knowledge graph",     "Knowledge Graph"),
        ("🔄  Translating resources",         "Translation"),
        ("📊  Assessing complexity",          "Assessment"),
        ("🛡️   Security analysis",            "Security"),
        ("📋  Compliance evaluation",         "Compliance"),
        ("💰  FinOps analysis",               "FinOps"),
        ("✅  Validation",                    "Validation"),
        ("🔬  Drift baseline",                "Drift Analysis"),
        ("📅  Migration planning",            "Planning"),
        ("🏗️   Generating Terraform",         "Terraform Gen"),
        ("📄  Generating reports",            "Reporting"),
        ("🤖  AI analysis",                   "AI Analysis"),
    ]
    if mode != "migrate":
        stages = [(label, key) for label, key in stages if key != "Terraform Gen"]

    results: dict[str, Any] = {"terraform": None}

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    ) as progress:

        for label, key in stages:
            task = progress.add_task(label, total=None)
            stage_start = time.perf_counter()

            # ── 1. Ingest ─────────────────────────────────────────────────
            if key == "Ingestion":
                pipeline = IngestionPipeline(settings=get_settings())
                ingestion = pipeline.run(source_path)
                results["ingestion"] = ingestion

                provider_counts = Counter(
                    r.source_provider.value for r in ingestion.graph.resources.values()
                )
                if provider_counts:
                    source_provider = CloudProvider(provider_counts.most_common(1)[0][0])
                if mode != "migrate":
                    # Analyze-only has no real migration target: force
                    # same-cloud so translation takes the identity path
                    # (see Translation stage below) instead of silently
                    # running a real cross-cloud capability matrix against
                    # whatever --target happens to default to.
                    target_provider = source_provider

                event_bus.publish(Event(
                    event_type=EventType.PARSING_COMPLETED,
                    source="cli",
                    data={"resources": len(ingestion.graph.resources)},
                ))

            # ── 2. Discovery / Enrichment ─────────────────────────────────
            elif key == "Discovery":
                ingestion = results["ingestion"]
                DiscoveryEngine().enrich(ingestion.graph)

            # ── 3. Knowledge Graph ────────────────────────────────────────
            elif key == "Knowledge Graph":
                ingestion = results["ingestion"]
                results["kg"] = KnowledgeGraphEngine().analyze(ingestion.graph)

            # ── 4. Translation ────────────────────────────────────────────
            elif key == "Translation":
                ingestion = results["ingestion"]
                if source_provider is target_provider:
                    # Same-cloud analysis (e.g. --mode analyze with no real
                    # migration target): no capability matrix exists for a
                    # provider mapped to itself, so skip straight to an
                    # identity report instead of erroring.
                    results["translation"] = TranslationEngine.build_identity_report(
                        ingestion.graph, source_provider
                    )
                else:
                    matrix = load_builtin_matrix(source_provider, target_provider)
                    results["translation"] = TranslationEngine(matrix=matrix).translate(ingestion.graph)

            # ── 5. Assessment ─────────────────────────────────────────────
            elif key == "Assessment":
                ingestion = results["ingestion"]
                translation = results["translation"]
                assessment = AssessmentEngine().assess(ingestion.graph, translation)
                results["assessment"] = assessment
                results["business_impact"] = BusinessImpactAnalyzer().analyze(ingestion.graph, assessment)
                results["tech_debt"] = TechnicalDebtAnalyzer().analyze(ingestion.graph, translation)
                results["readiness"] = ReadinessAssessor().assess(ingestion.graph, assessment, translation)

                event_bus.publish(Event(
                    event_type=EventType.ASSESSMENT_COMPLETED,
                    source="cli",
                    data={
                        "complexity": assessment.overall_complexity_score,
                        "risk": assessment.risk_level.value,
                        "blockers": len(assessment.blockers),
                    },
                ))

            # ── 6. Security ───────────────────────────────────────────────
            elif key == "Security":
                graph = results["ingestion"].graph
                results["security"] = SecurityEngine().analyze(graph)

                from migration_factory.ai.rca import RootCauseAnalyzer

                policy_report = PolicyEngine().evaluate(graph)
                results["policy"] = policy_report
                results["rca"] = RootCauseAnalyzer().analyze(
                    graph=graph,
                    policy_report=policy_report,
                    security_report=results["security"],
                )

            # ── 7. Compliance ─────────────────────────────────────────────
            elif key == "Compliance":
                results["compliance"] = ComplianceEngine().evaluate(results["ingestion"].graph)

            # ── 8. FinOps ─────────────────────────────────────────────────
            elif key == "FinOps":
                results["finops"] = FinOpsEngine(
                    target_provider=target_provider
                ).analyze(results["ingestion"].graph)

            # ── 9. Validation ─────────────────────────────────────────────
            elif key == "Validation":
                results["validation"] = ValidationEngine().validate(results["ingestion"].graph)

            # ── 9b. Drift baseline ────────────────────────────────────────
            elif key == "Drift Analysis":
                # No second (live/actual) state source exists in a single
                # `poc` run, so this establishes a self-comparison baseline
                # (desired == actual) rather than detecting real drift --
                # real drift detection needs a live discovery re-scan to
                # diff against, which is what /api/v1/discover/* is for.
                graph = results["ingestion"].graph
                results["drift"] = DriftDetectionEngine().detect(desired=graph, actual=graph)

            # ── 10. Planning ──────────────────────────────────────────────
            elif key == "Planning":
                ingestion = results["ingestion"]
                assessment = results["assessment"]
                translation = results["translation"]
                results["plan"] = MigrationPlanner().plan(ingestion.graph, assessment, translation)
                results["rollback"] = RollbackPlanner().plan(ingestion.graph, translation)

            # ── 11. Terraform Generation ──────────────────────────────────
            elif key == "Terraform Gen":
                ingestion = results["ingestion"]
                translation = results["translation"]
                gen = TerraformGenerator(
                    target_provider=target_provider,
                    project_id="your-gcp-project",
                )
                results["terraform"] = gen.generate(ingestion.graph, translation)
                if output_dir:
                    tf_dir = output_dir / "terraform"
                    gen.write(results["terraform"], tf_dir)

                event_bus.publish(Event(
                    event_type=EventType.TERRAFORM_GENERATED,
                    source="cli",
                    data={
                        "files": len(results["terraform"].files),
                        "resources": results["terraform"].generated_resources,
                    },
                ))

            # ── 12. Reporting ─────────────────────────────────────────────
            elif key == "Reporting":
                report = ReportingEngine().generate(
                    assessment=results.get("assessment"),
                    translation=results.get("translation"),
                    security=results.get("security"),
                    compliance=results.get("compliance"),
                    finops=results.get("finops"),
                    validation=results.get("validation"),
                    terraform=results.get("terraform"),
                )
                results["report"] = report
                if output_dir:
                    output_dir.mkdir(parents=True, exist_ok=True)
                    (output_dir / "migration-report.md").write_text(report.to_markdown(), encoding="utf-8")
                    report_direction = (
                        f"{source_provider.value.upper()} Analysis"
                        if mode != "migrate"
                        else f"{source_provider.value.upper()} → {target_provider.value.upper()}"
                    )
                    dashboard_html = ReportingEngine().to_html_dashboard(
                        assessment=results.get("assessment"),
                        security=results.get("security"),
                        compliance=results.get("compliance"),
                        finops=results.get("finops"),
                        plan=results.get("plan"),
                        translation=results.get("translation"),
                        direction=report_direction,
                    )
                    (output_dir / "migration-report.html").write_text(dashboard_html, encoding="utf-8")
                    mermaid_diagram = generate_mermaid_diagram(results["ingestion"].graph)
                    (output_dir / "dependency-graph.mmd").write_text(mermaid_diagram, encoding="utf-8")

            # ── 13. AI Analysis ────────────────────────────────────────────
            elif key == "AI Analysis":
                from migration_factory.ai.engine import AIEngine

                ai_engine = AIEngine()
                results["ai_mode"] = "ai" if ai_engine.is_available else "rule_based"

                graph = results["ingestion"].graph
                translation = results["translation"]
                assessment = results["assessment"]
                cost_summary = results["finops"].cost_summary

                results["ai_risks"] = ai_engine.analyze_migration_risks(graph, translation, assessment)
                results["ai_optimizations"] = ai_engine.suggest_optimizations(
                    graph, translation, cost_summary.source_monthly_total, cost_summary.target_monthly_total
                )
                results["ai_summary"] = ai_engine.generate_architecture_summary(graph)

            metrics.histogram("stage_duration_seconds", time.perf_counter() - stage_start, stage=key)
            progress.update(task, completed=True)

    # ─────────────────────────────────────────────────────────────────────────
    # RESULTS DISPLAY
    # ─────────────────────────────────────────────────────────────────────────
    ingestion = results["ingestion"]
    assessment = results["assessment"]
    translation = results["translation"]
    security = results["security"]
    compliance = results["compliance"]
    finops = results["finops"]
    plan = results["plan"]
    rollback = results["rollback"]
    readiness = results["readiness"]
    kg = results["kg"]

    console.print()

    # ── Executive Summary ─────────────────────────────────────────────────
    source_label = source_provider.value.upper() if ingestion.graph.resources else "CLOUD"
    if mode != "migrate":
        direction = f"{source_label} Analysis"
    else:
        target_label = target_provider.value.upper()
        direction = f"{source_label} → {target_label}"

    summary = Table(show_header=False, box=rich_box.ROUNDED, border_style="cyan", padding=(0, 1))
    summary.add_column("", style="dim", min_width=28)
    summary.add_column("", style="bold")

    def _risk_color(level: str) -> str:
        return {"low": "green", "medium": "yellow", "high": "red", "critical": "bold red"}.get(level, "white")

    def _score_color(score: int, invert: bool = False) -> str:
        if invert:
            return "green" if score <= 30 else "yellow" if score <= 60 else "red"
        return "green" if score >= 70 else "yellow" if score >= 40 else "red"

    summary.add_row("Migration", direction)
    summary.add_row("Source file", str(source_path.name))
    summary.add_row("Resources discovered", str(len(ingestion.graph.resources)))
    summary.add_row("", "")
    summary.add_row(
        "Complexity score",
        f"[{_score_color(assessment.overall_complexity_score, invert=True)}]{assessment.overall_complexity_score}/100[/]"
    )
    summary.add_row(
        "Risk level",
        f"[{_risk_color(assessment.risk_level.value)}]{assessment.risk_level.value.upper()}[/]"
    )
    summary.add_row(
        "Migration confidence",
        f"[{_score_color(plan.confidence.overall_confidence)}]{plan.confidence.overall_confidence}/100[/]"
    )
    if readiness.overall_readiness == "ready":
        _r_color = "green"
    elif readiness.overall_readiness == "partially_ready":
        _r_color = "yellow"
    else:
        _r_color = "red"
    summary.add_row(
        "Readiness",
        f"[{_r_color}]{readiness.overall_readiness.replace('_', ' ').upper()}[/] ({readiness.readiness_score}%)"
    )
    summary.add_row("", "")
    summary.add_row(
        "Security score",
        f"[{_score_color(security.security_score)}]{security.security_score}/100[/] — {security.risk_level.value}"
    )
    summary.add_row(
        "Compliance",
        f"[{_score_color(int(compliance.overall_compliance_score))}]{compliance.overall_compliance_score:.0f}%[/] overall"
    )
    summary.add_row("", "")
    s = finops.cost_summary
    summary.add_row("Monthly cost (source)", f"${s.source_monthly_total:,.0f}")
    summary.add_row("Monthly cost (target)", f"${s.target_monthly_total:,.0f}")
    savings_color = "green" if s.monthly_savings > 0 else "red"
    summary.add_row("Monthly savings", f"[{savings_color}]${s.monthly_savings:,.0f}[/]")
    summary.add_row("Break-even", f"{s.break_even_months:.1f} months")
    summary.add_row("", "")
    summary.add_row("Estimated downtime", f"{plan.cutover_plan.total_downtime_minutes} minutes")
    summary.add_row("Migration waves", str(len(plan.waves)))
    summary.add_row("Rollback duration", f"~{rollback.estimated_duration_minutes} minutes")
    summary.add_row("Blockers", f"[{'red' if assessment.blockers else 'green'}]{len(assessment.blockers)}[/]")

    console.print(Panel(summary, title="[bold cyan]Executive Summary[/bold cyan]", border_style="cyan"))

    # ── Translation Breakdown ─────────────────────────────────────────────
    console.print()
    tsummary = translation.summary
    t_table = Table(title="Translation Plan", box=rich_box.SIMPLE_HEAD, title_style="bold")
    t_table.add_column("Status", style="bold", width=12)
    t_table.add_column("Count", justify="right", width=6)
    t_table.add_column("Resources")

    status_colors = {"supported": "green", "partial": "yellow", "manual": "orange3", "unsupported": "red"}
    status_icons = {"supported": "✓", "partial": "◐", "manual": "⚠", "unsupported": "✗"}

    for status, count in tsummary.items():
        if count == 0:
            continue
        resources_of_status = [tr.resource_name for tr in translation.results if tr.status.value == status]
        col = status_colors.get(status, "white")
        icon = status_icons.get(status, "?")
        t_table.add_row(
            f"[{col}]{icon} {status.capitalize()}[/]",
            f"[{col}]{count}[/]",
            f"[dim]{', '.join(resources_of_status[:5])}{'...' if len(resources_of_status) > 5 else ''}[/]",
        )
    console.print(t_table)

    # ── Migration Phases ──────────────────────────────────────────────────
    console.print()
    wave_table = Table(title="Migration Wave Plan", box=rich_box.SIMPLE_HEAD, title_style="bold")
    wave_table.add_column("Wave", width=6, justify="right")
    wave_table.add_column("Name", min_width=28)
    wave_table.add_column("Resources", justify="right", width=10)
    wave_table.add_column("Mode", width=12)
    wave_table.add_column("Est. Duration")
    wave_table.add_column("Validation Checkpoint")

    for wave in plan.waves:
        mode_color = "cyan" if wave.can_parallelize else "yellow"
        mode_label = "⚡ Parallel" if wave.can_parallelize else "→ Sequential"
        hours = wave.estimated_duration_hours
        duration = f"{hours:.1f}h" if hours >= 1 else f"{int(hours * 60)}m"
        checkpoint = wave.validation_checkpoints[0][:45] + "…" if wave.validation_checkpoints else "—"
        wave_table.add_row(
            str(wave.wave_number),
            wave.name,
            str(len(wave.resource_ids)),
            f"[{mode_color}]{mode_label}[/]",
            duration,
            f"[dim]{checkpoint}[/]",
        )
    console.print(wave_table)

    # ── Per-Resource Assessment ───────────────────────────────────────────
    console.print()
    res_table = Table(title="Resource Assessment", box=rich_box.SIMPLE_HEAD, title_style="bold")
    res_table.add_column("Resource", min_width=20)
    res_table.add_column("Type", min_width=18)
    res_table.add_column("Score", justify="right", width=7)
    res_table.add_column("Strategy", width=12)
    res_table.add_column("Target Service", min_width=20)
    res_table.add_column("Downtime", width=8)
    res_table.add_column("Blockers", justify="right", width=8)

    strategy_colors = {"rehost": "green", "replatform": "yellow", "manual": "red"}
    downtime_colors = {"none": "green", "low": "cyan", "medium": "yellow", "high": "red"}

    tr_index = {tr.resource_id: tr for tr in translation.results}
    for ra in assessment.resource_assessments:
        tr = tr_index.get(ra.resource_id)
        target_svc = tr.target_service or "—" if tr else "—"
        s_color = strategy_colors.get(ra.strategy.value, "white")
        d_color = downtime_colors.get(ra.downtime.value, "white")
        score_color = "green" if ra.complexity_score <= 30 else "yellow" if ra.complexity_score <= 60 else "red"
        res_table.add_row(
            ra.resource_name[:20],
            ra.canonical_type.value,
            f"[{score_color}]{ra.complexity_score}[/]",
            f"[{s_color}]{ra.strategy.value}[/]",
            target_svc[:20],
            f"[{d_color}]{ra.downtime.value}[/]",
            f"[{'red' if ra.blockers else 'green'}]{len(ra.blockers)}[/]",
        )
    console.print(res_table)

    # ── Security & Compliance ─────────────────────────────────────────────
    if security.iam_findings or security.secret_findings or security.firewall_findings:
        console.print()
        sec_table = Table(title="Security Findings", box=rich_box.SIMPLE_HEAD, title_style="bold red")
        sec_table.add_column("Severity", width=10)
        sec_table.add_column("Type", width=16)
        sec_table.add_column("Resource", min_width=20)
        sec_table.add_column("Finding")

        sev_colors = {"critical": "bold red", "high": "red", "medium": "yellow", "low": "dim"}

        for f in security.iam_findings[:5]:
            sc = sev_colors.get(f.severity.value, "white")
            sec_table.add_row(f"[{sc}]{f.severity.value.upper()}[/]", "IAM", f.resource_name[:20], f.message[:60])
        for f in security.secret_findings[:3]:
            sec_table.add_row("[bold red]CRITICAL[/]", "Secret", f.resource_name[:20], f"Potential secret at {f.attribute_path}")
        for f in security.firewall_findings[:3]:
            sc = sev_colors.get(f.severity.value, "white")
            sec_table.add_row(f"[{sc}]{f.severity.value.upper()}[/]", "Firewall", f.resource_name[:20], f.message[:60])

        console.print(sec_table)

    # ── Root Cause Analysis ────────────────────────────────────────────────
    rca_report = results.get("rca")
    if rca_report and rca_report.findings:
        from rich.markup import escape

        rca_table = Table(
            title=f"Root Cause Analysis ({rca_report.total_findings} findings)",
            box=rich_box.SIMPLE_HEAD, title_style="bold magenta",
        )
        rca_table.add_column("Severity", width=10)
        rca_table.add_column("Finding", min_width=24)
        rca_table.add_column("Root Cause", min_width=30)
        rca_table.add_column("Remediation")

        rca_sev_colors = {"critical": "bold red", "high": "red", "medium": "yellow", "low": "dim"}
        for finding in rca_report.findings[:8]:
            sc = rca_sev_colors.get(finding.severity.value, "white")
            rca_table.add_row(
                f"[{sc}]{finding.severity.value.upper()}[/]",
                escape(finding.title[:40]),
                escape(finding.root_cause[:50]),
                escape(finding.remediation_steps[0][:50]) if finding.remediation_steps else "—",
            )
        console.print()
        console.print(rca_table)

    # ── Blockers ──────────────────────────────────────────────────────────
    if assessment.blockers:
        console.print()
        console.print(Panel(
            "\n".join(f"  [yellow]⚠[/yellow]  {b}" for b in assessment.blockers),
            title=f"[bold yellow]Blockers ({len(assessment.blockers)})[/bold yellow]",
            border_style="yellow",
        ))

    # ── Knowledge Graph Stats ─────────────────────────────────────────────
    console.print()
    kg_table = Table(title="Infrastructure Knowledge Graph", box=rich_box.SIMPLE_HEAD, title_style="bold")
    kg_table.add_column("Metric", min_width=28)
    kg_table.add_column("Value", justify="right")
    kg_table.add_row("Total dependency edges", str(kg.total_edges))
    kg_table.add_row("Critical resources", str(len(kg.critical_resources)))
    kg_table.add_row("Application groups", str(len(kg.application_groups)))
    if kg.dependency_type_counts:
        for dep_type, count in sorted(kg.dependency_type_counts.items(), key=lambda x: -x[1]):
            kg_table.add_row(f"  {dep_type} edges", str(count))
    console.print(kg_table)

    # ── Generated Artifacts ───────────────────────────────────────────────
    if terraform := results.get("terraform"):
        console.print()
        art_table = Table(
            title=f"Generated Terraform ({target_label} Target)", box=rich_box.SIMPLE_HEAD, title_style="bold green"
        )
        art_table.add_column("File", min_width=20)
        art_table.add_column("Description")
        art_table.add_column("Lines", justify="right", width=6)
        for gf in terraform.files:
            art_table.add_row(
                f"[green]{gf.filename}[/]",
                gf.description,
                str(len(gf.content.split('\n')))
            )
        art_table.add_row("", "", "")
        art_table.add_row(
            f"[green]{terraform.generated_resources}[/] resources generated",
            f"[dim]{terraform.skipped_resources} skipped (manual/unsupported)[/]",
            ""
        )
        console.print(art_table)

    # ── Compliance Summary ────────────────────────────────────────────────
    console.print()
    comp_table = Table(title="Compliance Assessment", box=rich_box.SIMPLE_HEAD, title_style="bold")
    comp_table.add_column("Framework", width=10)
    comp_table.add_column("Score", justify="right", width=8)
    comp_table.add_column("Status", width=14)
    comp_table.add_column("Failed Checks")
    for fr in compliance.framework_results:
        sc = fr.compliance_score
        status = "✓ Compliant" if sc >= 80 else "✗ Non-compliant"
        sc_color = "green" if sc >= 80 else "yellow" if sc >= 60 else "red"
        st_color = "green" if sc >= 80 else "red"
        failed = ", ".join(fr.failed_check_ids[:3]) or "—"
        comp_table.add_row(
            fr.framework,
            f"[{sc_color}]{sc:.0f}%[/]",
            f"[{st_color}]{status}[/]",
            f"[dim]{failed}[/]",
        )
    console.print(comp_table)

    # ── Recommendation ────────────────────────────────────────────────────
    console.print()
    console.print(Panel(
        f"[bold]{assessment.recommendation}[/bold]",
        title="[bold cyan]Recommendation[/bold cyan]",
        border_style="cyan",
    ))

    # ── Drift baseline ─────────────────────────────────────────────────────
    drift = results.get("drift")
    if drift:
        console.print()
        console.print(f"[dim]Drift baseline established: {drift.total_resources_checked} resources tracked[/dim]")
        if not drift.drift_detected:
            console.print(
                "[dim]No drift detected against baseline (self-comparison — "
                "compare a live /api/v1/discover/* scan for real drift)[/dim]"
            )

    # ── AI Insights ────────────────────────────────────────────────────────
    ai_risks = results.get("ai_risks")
    ai_opts = results.get("ai_optimizations")
    ai_sum = results.get("ai_summary")

    if ai_risks or ai_opts or ai_sum:
        from rich.markup import escape

        ai_content = ""
        if ai_sum and ai_sum.content:
            ai_content += f"[bold]Architecture:[/bold]\n{escape(ai_sum.content[:300])}\n\n"
        if ai_risks and ai_risks.content:
            ai_content += f"[bold]Key Risks:[/bold]\n{escape(ai_risks.content[:400])}\n\n"
        if ai_opts and ai_opts.content:
            ai_content += f"[bold]Optimizations:[/bold]\n{escape(ai_opts.content[:300])}"

        if ai_content.strip():
            mode_label = "🤖 AI-Powered" if results.get("ai_mode") == "ai" else "🔍 Rule-based"
            console.print()
            console.print(Panel(
                ai_content.strip(),
                title=f"[bold magenta]AI Analysis ({mode_label})[/bold magenta]",
                border_style="magenta",
            ))

    # ── Output files ──────────────────────────────────────────────────────
    if output_dir:
        console.print()
        terraform_line = (
            f"[green]✓[/green]  [bold]Terraform:[/bold]       {output_dir}/terraform/\n"
            if results.get("terraform") is not None
            else ""
        )
        console.print(Panel(
            f"{terraform_line}"
            f"[green]✓[/green]  [bold]Markdown report:[/bold] {output_dir}/migration-report.md\n"
            f"[green]✓[/green]  [bold]HTML report:[/bold]     {output_dir}/migration-report.html\n"
            f"[green]✓[/green]  [bold]Mermaid diagram:[/bold] {output_dir}/dependency-graph.mmd",
            title="[bold green]Output Artifacts[/bold green]",
            border_style="green",
        ))

    total_elapsed = time.perf_counter() - pipeline_start
    metrics.gauge("pipeline_duration_seconds", total_elapsed)
    metrics.gauge("pipeline_resource_count", len(ingestion.graph.resources))

    event_bus.publish(Event(
        event_type=EventType.PIPELINE_COMPLETED,
        source="cli",
        data={
            "total_resources": len(ingestion.graph.resources),
            "savings": s.monthly_savings,
            "direction": direction,
        },
    ))

    console.print()
    console.print(
        f"[dim]Pipeline: {total_elapsed:.2f}s | "
        f"Avg per resource: {total_elapsed / max(1, len(ingestion.graph.resources)) * 1000:.0f}ms[/dim]"
    )
    console.print(Panel.fit(
        f"[bold green]POC Complete[/bold green]  "
        f"[dim]{direction} · "
        f"{len(ingestion.graph.resources)} resources · "
        f"{len(plan.waves)} waves · "
        f"{plan.cutover_plan.total_downtime_minutes}min downtime · "
        f"${s.monthly_savings:,.0f}/month savings[/dim]",
        border_style="green",
    ))
    console.print()


if __name__ == "__main__":
    raise SystemExit(main())
