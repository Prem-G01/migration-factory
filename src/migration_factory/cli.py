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

from migration_factory.core.config import get_settings
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

    return parser


def main(argv: list[str] | None = None) -> int:
    settings = get_settings()
    configure_logging(settings)
    args = _build_parser().parse_args(argv)

    if args.command == "ingest":
        return _run_ingest(args, settings)

    if args.command == "poc":
        return _run_poc(args, settings)

    return 1


# ── ingest ───────────────────────────────────────────────────────────────────

def _run_ingest(args: argparse.Namespace, settings: object) -> int:
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


# ── poc ──────────────────────────────────────────────────────────────────────

def _run_poc(args: argparse.Namespace, settings: object) -> int:  # noqa: ANN001
    from rich import box
    from rich.console import Console
    from rich.panel import Panel

    console = Console(no_color=getattr(args, "no_color", False))

    # ── Banner ────────────────────────────────────────────────────────────
    console.print()
    console.print(Panel.fit(
        "[bold cyan]Migration Factory[/bold cyan]  [dim]AI-Powered Multi-Cloud Infrastructure Migration[/dim]\n"
        f"[dim]Source:[/dim] {args.source_path}   "
        f"[dim]Target:[/dim] [bold]{args.target.upper()}[/bold]",
        border_style="cyan",
    ))
    console.print()

    source_path = args.source_path
    target_cloud = args.target
    output_dir = args.output
    mode = args.mode

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
    console: object,
    source_path: Path,
    target_cloud: str,
    output_dir: Path | None,
    box: object,
    mode: str = "migrate",
) -> None:
    from collections import Counter

    from rich import box as rich_box
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
    from rich.table import Table

    console = console  # type: ignore[assignment]

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
    from migration_factory.finops.engine import FinOpsEngine
    from migration_factory.knowledge_graph.engine import KnowledgeGraphEngine
    from migration_factory.pipeline import IngestionPipeline
    from migration_factory.planner.engine import MigrationPlanner
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
        ("📅  Migration planning",            "Planning"),
        ("🏗️   Generating Terraform",         "Terraform Gen"),
        ("📄  Generating reports",            "Reporting"),
    ]
    if mode != "migrate":
        stages = [(label, key) for label, key in stages if key != "Terraform Gen"]

    results: dict[str, object] = {"terraform": None}

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    ) as progress:

        for label, key in stages:
            task = progress.add_task(label, total=None)

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

            # ── 6. Security ───────────────────────────────────────────────
            elif key == "Security":
                results["security"] = SecurityEngine().analyze(results["ingestion"].graph)

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
                    (output_dir / "migration-report.md").write_text(
                        report.to_markdown(), encoding="utf-8"
                    )
                    (output_dir / "migration-report.html").write_text(
                        ReportingEngine().to_html(report), encoding="utf-8"
                    )
                    (output_dir / "dependency-graph.mmd").write_text(
                        generate_mermaid_diagram(results["ingestion"].graph), encoding="utf-8"
                    )

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

    console.print()
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
