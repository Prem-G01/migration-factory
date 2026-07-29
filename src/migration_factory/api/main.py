"""FastAPI REST layer over the Migration Factory pipeline.

Wraps the same engines the CLI (`migration_factory.cli`) drives, but headless
(no Rich console output) and returning JSON instead of a terminal report.
Run results are persisted to PostgreSQL (see `database.py`) so they survive
an API process restart; schema changes go through Alembic (`alembic/`).
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import shutil
import subprocess
import tempfile
import time
import uuid
import zipfile
from collections import Counter
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from migration_factory.ai.engine import AIEngine
from migration_factory.api.database import MigrationRun, get_run, get_session, save_run
from migration_factory.api.database import delete_run as db_delete_run
from migration_factory.api.database import list_runs as db_list_runs
from migration_factory.assessment.engine import AssessmentEngine
from migration_factory.compliance.engine import ComplianceEngine
from migration_factory.core.config import get_settings
from migration_factory.core.exceptions import MigrationFactoryError, ParserError
from migration_factory.core.logging import get_logger
from migration_factory.discovery.engine import DiscoveryEngine
from migration_factory.domain.enums import CloudProvider
from migration_factory.events.engine import Event, EventBus, EventType
from migration_factory.finops.engine import FinOpsEngine
from migration_factory.knowledge_graph.engine import KnowledgeGraphEngine
from migration_factory.pipeline import IngestionPipeline
from migration_factory.planner.engine import MigrationPlanner
from migration_factory.reporting.engine import ReportingEngine
from migration_factory.rollback.engine import RollbackPlanner
from migration_factory.security.engine import SecurityEngine
from migration_factory.terraform_gen.engine import GeneratedFile, TerraformGenerator
from migration_factory.translation.engine import TranslationEngine
from migration_factory.translation.matrix import load_builtin_matrix
from migration_factory.validation.engine import ValidationEngine

_event_bus = EventBus()
_logger = get_logger(__name__)


def _run_migrations_sync() -> None:
    """Applies pending Alembic migrations against the configured database.

    Run in a worker thread by the lifespan hook below: Alembic's env.py
    calls `asyncio.run(...)` internally, which cannot nest inside the event
    loop this hook already runs in.
    """
    alembic_ini = Path.cwd() / "alembic.ini"
    if not alembic_ini.exists():
        _logger.warning("alembic_ini_not_found", cwd=str(Path.cwd()))
        return
    from alembic.config import Config

    from alembic import command

    try:
        command.upgrade(Config(str(alembic_ini)), "head")
    except Exception:
        _logger.exception("startup_migration_failed")


@asynccontextmanager
async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
    # The Docker image runs `alembic upgrade head` via docker-entrypoint.sh
    # before uvicorn starts. Platforms with no separate release-phase step
    # (e.g. Render's free tier with a bare `uvicorn ...` Start Command) skip
    # that entirely, leaving a fresh DB with no migration_runs table. Run it
    # here instead so a plain `uvicorn` start is still correct on its own --
    # skipped under pytest since tests provision their own in-memory sqlite
    # engine directly (see tests/unit/test_api.py) and would otherwise race
    # this against a different, real database.
    if "PYTEST_CURRENT_TEST" not in os.environ:
        await asyncio.to_thread(_run_migrations_sync)
    yield


app = FastAPI(
    title="Migration Factory API",
    version="2.0.3",
    description="REST API for the AI-Powered Multi-Cloud Infrastructure Migration Factory",
    lifespan=_lifespan,
)
app.add_middleware(
    CORSMiddleware,
    # :5173/:3000 are the Vite/CRA dev servers; bare "http://localhost" is the
    # Docker Compose path (nginx serves the built frontend on port 80, and
    # browsers omit the port from the Origin header for the scheme's default).
    # github.io is the production GitHub Pages frontend.
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://localhost",
        "https://prem-g01.github.io",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root() -> RedirectResponse:
    return RedirectResponse(url="/docs")


@app.get("/health")
async def health_shortcut() -> RedirectResponse:
    return RedirectResponse(url="/api/v1/health")


_Target = Literal["gcp", "aws", "analyze_only"]


def _direction_label(source_provider: CloudProvider, target_provider: CloudProvider) -> str:
    return f"{source_provider.value.upper()} → {target_provider.value.upper()}"


def _build_terraform_zip(terraform_files: list[GeneratedFile]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for generated_file in terraform_files:
            zf.writestr(generated_file.filename, generated_file.content.encode("utf-8"))
    return buffer.getvalue()


def _run_pipeline(source_path: Path, source_filename: str, target: _Target | None) -> MigrationRun:
    """Ingest -> discover -> translate -> assess -> secure -> comply ->
    cost -> validate -> plan -> (optionally) generate Terraform -> report.
    Mirrors the CLI's `_poc_pipeline` stage order, without Rich rendering.
    A missing/None target means analyze_only: same-cloud analysis, no
    Terraform generated. Returns an unsaved MigrationRun row; the caller
    persists it.
    """
    started_at = time.perf_counter()
    settings = get_settings()
    ingestion = IngestionPipeline(settings=settings).run(source_path)

    provider_counts = Counter(r.source_provider.value for r in ingestion.graph.resources.values())
    source_provider = (
        CloudProvider(provider_counts.most_common(1)[0][0]) if provider_counts else CloudProvider.AWS
    )

    if target is None or target == "analyze_only":
        target_provider = source_provider
        mode = "analyze"
    else:
        target_provider = CloudProvider.GCP if target == "gcp" else CloudProvider.AWS
        mode = "migrate"

    DiscoveryEngine().enrich(ingestion.graph)
    knowledge_graph = KnowledgeGraphEngine().analyze(ingestion.graph)

    if source_provider is target_provider:
        # No capability matrix exists for a provider mapped to itself
        # (there is no aws_to_aws.json) — same-cloud analysis is an
        # identity translation instead of a matrix lookup.
        translation = TranslationEngine.build_identity_report(ingestion.graph, source_provider)
    else:
        matrix = load_builtin_matrix(source_provider, target_provider)
        translation = TranslationEngine(matrix=matrix).translate(ingestion.graph)

    assessment = AssessmentEngine().assess(ingestion.graph, translation)
    security = SecurityEngine().analyze(ingestion.graph)
    compliance = ComplianceEngine().evaluate(ingestion.graph)
    finops = FinOpsEngine(target_provider=target_provider).analyze(ingestion.graph)
    validation = ValidationEngine().validate(ingestion.graph)
    plan = MigrationPlanner().plan(ingestion.graph, assessment, translation)
    rollback = RollbackPlanner().plan(ingestion.graph, translation)

    terraform_zip_bytes: bytes | None = None
    terraform_report = None
    if mode == "migrate":
        generator = TerraformGenerator(target_provider=target_provider, project_id="api-run-project")
        terraform_report = generator.generate(ingestion.graph, translation)
        terraform_zip_bytes = _build_terraform_zip(terraform_report.files)

    direction = _direction_label(source_provider, target_provider)

    html_report = ReportingEngine().to_html_dashboard(
        assessment=assessment,
        security=security,
        compliance=compliance,
        finops=finops,
        plan=plan,
        translation=translation,
        direction=direction,
    )

    ai_engine = AIEngine()
    ai_risks = ai_engine.analyze_migration_risks(ingestion.graph, translation, assessment)
    ai_optimizations = ai_engine.suggest_optimizations(
        ingestion.graph, translation, finops.cost_summary.source_monthly_total, finops.cost_summary.target_monthly_total
    )
    ai_summary = ai_engine.generate_architecture_summary(ingestion.graph)
    ai_analysis = {
        "risks": ai_risks.content,
        "optimizations": ai_optimizations.content,
        "summary": ai_summary.content,
        "mode": "ai" if ai_engine.is_available else "rule_based",
    }

    run_id = str(uuid.uuid4())
    duration_seconds = round(time.perf_counter() - started_at, 2)
    created_at = datetime.now(UTC)

    summary: dict[str, Any] = {
        "resources": len(ingestion.graph.resources),
        "complexity_score": assessment.overall_complexity_score,
        "risk_level": assessment.risk_level.value,
        "confidence_score": plan.confidence.overall_confidence,
        "security_score": security.security_score,
        "compliance_score": compliance.overall_compliance_score,
        "monthly_savings": finops.cost_summary.monthly_savings,
        "downtime_minutes": plan.cutover_plan.total_downtime_minutes,
        "waves": len(plan.waves),
        "blockers": len(assessment.blockers),
        "duration_seconds": duration_seconds,
    }

    # Every nested value must be plain JSON (dicts/lists/str/int/float/bool),
    # not Pydantic model instances: this dict lands in a SQLAlchemy JSON
    # column via plain json.dumps, not FastAPI's jsonable_encoder.
    assessment_dict = assessment.model_dump(mode="json")
    target_service_by_resource = {r.resource_id: r.target_service for r in translation.results}
    for resource_assessment in assessment_dict["resource_assessments"]:
        # ResourceAssessment has no target_service field of its own — that
        # lives on the matching TranslationResult. Merged in here so the
        # dashboard's resource table doesn't need a second lookup.
        resource_assessment["target_service"] = target_service_by_resource.get(
            resource_assessment["resource_id"]
        )

    full_report: dict[str, Any] = {
        "run_id": run_id,
        "status": "completed",
        "mode": mode,
        "direction": direction,
        "created_at": created_at.isoformat(),
        "duration_seconds": duration_seconds,
        "source_provider": source_provider.value,
        "target_provider": target_provider.value,
        "unsupported_resources": ingestion.unsupported_resources,
        "knowledge_graph": knowledge_graph.model_dump(mode="json"),
        "translation_summary": translation.summary,
        "translation_results": [r.model_dump(mode="json") for r in translation.results],
        "assessment": assessment_dict,
        "security": security.model_dump(mode="json"),
        "compliance": compliance.model_dump(mode="json"),
        "finops": finops.model_dump(mode="json"),
        "validation": validation.model_dump(mode="json"),
        "plan": plan.model_dump(mode="json"),
        "rollback": rollback.model_dump(mode="json"),
        "terraform_available": terraform_zip_bytes is not None,
        "summary": summary,
        "ai_analysis": ai_analysis,
    }

    _event_bus.publish(Event(
        event_type=EventType.PIPELINE_COMPLETED,
        source="api",
        data={
            "total_resources": len(ingestion.graph.resources),
            "savings": finops.cost_summary.monthly_savings,
            "direction": direction,
        },
    ))

    return MigrationRun(
        id=run_id,
        created_at=created_at,
        direction=direction,
        source_file=source_filename,
        target=target or "analyze_only",
        status="completed",
        summary_json=summary,
        report_json=full_report,
        html_report=html_report,
        terraform_zip_bytes=terraform_zip_bytes,
    )


@app.post("/api/v1/analyze")
async def analyze(
    file: UploadFile = File(..., description="Terraform state (.tfstate), JSON, or CSV inventory file"),
    target: _Target | None = Form(None, description='One of: "gcp", "aws", "analyze_only" (omit for analyze_only)'),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    suffix = Path(file.filename or "upload").suffix or ".tfstate"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = Path(tmp.name)

    try:
        run = _run_pipeline(tmp_path, file.filename or "upload", target)
    except ParserError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MigrationFactoryError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Pipeline failed: {exc}") from exc
    finally:
        tmp_path.unlink(missing_ok=True)

    await save_run(session, run)

    return {
        "run_id": run.id,
        "status": run.status,
        "direction": run.direction,
        "duration_seconds": run.report_json["duration_seconds"],
        "summary": run.summary_json,
    }


@app.get("/api/v1/report/{run_id}")
async def get_report(run_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    run = await get_run(session, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Unknown run_id: {run_id!r}")
    result: dict[str, Any] = run.report_json
    return result


@app.get("/api/v1/report/{run_id}/html", response_class=HTMLResponse)
async def get_report_html(run_id: str, session: AsyncSession = Depends(get_session)) -> HTMLResponse:
    run = await get_run(session, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Unknown run_id: {run_id!r}")
    return HTMLResponse(content=run.html_report)


@app.get("/api/v1/terraform/{run_id}")
async def get_terraform(run_id: str, session: AsyncSession = Depends(get_session)) -> StreamingResponse:
    run = await get_run(session, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Unknown run_id: {run_id!r}")

    if not run.terraform_zip_bytes:
        raise HTTPException(
            status_code=404,
            detail=f"No Terraform was generated for run {run_id!r} (analyze_only mode has no Terraform output)",
        )

    filename = f"migration-terraform-{run_id[:8]}.zip"
    return StreamingResponse(
        io.BytesIO(run.terraform_zip_bytes),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/v1/runs")
async def list_all_runs(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    runs = await db_list_runs(session)
    return {
        "runs": [
            {
                "run_id": run.id,
                "direction": run.direction,
                "mode": run.report_json.get("mode"),
                "created_at": run.created_at.isoformat(),
                **run.summary_json,
            }
            for run in runs
        ]
    }


@app.delete("/api/v1/runs/{run_id}")
async def delete_run_endpoint(run_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, bool]:
    deleted = await db_delete_run(session, run_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Unknown run_id: {run_id!r}")
    return {"deleted": True}


def _run_cli(args: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=30)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=f"{args[0]!r} CLI not found on this machine") from exc
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=400, detail=f"{args[0]!r} CLI timed out after 30s") from exc


@app.get("/api/v1/discover/aws")
def discover_aws(region: str = "us-east-1") -> dict[str, Any]:
    """Live AWS discovery: runs the AWS CLI directly (describe-instances +
    describe-vpcs + describe-security-groups) instead of requiring a
    pre-exported file upload. Plain `def`, not `async def` -- these are
    blocking subprocess calls (up to 30s each); FastAPI runs sync route
    functions in a worker thread so they don't block the event loop.
    """
    result = _run_cli(["aws", "ec2", "describe-instances", "--region", region, "--output", "json"])
    if result.returncode != 0:
        raise HTTPException(status_code=400, detail=f"AWS CLI failed: {result.stderr[:200]}")

    combined = json.loads(result.stdout)
    for extra_cmd in (
        ["aws", "ec2", "describe-vpcs", "--region", region, "--output", "json"],
        ["aws", "ec2", "describe-security-groups", "--region", region, "--output", "json"],
    ):
        extra_result = _run_cli(extra_cmd)
        if extra_result.returncode == 0:
            combined.update(json.loads(extra_result.stdout))

    with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False, encoding="utf-8") as f:
        json.dump(combined, f)
        tmp_path = Path(f.name)

    try:
        ingestion = IngestionPipeline(settings=get_settings()).run(tmp_path)
        return {
            "region": region,
            "resources_discovered": len(ingestion.graph.resources),
            "resource_types": sorted({r.source_type for r in ingestion.graph.resources.values()}),
            "message": (
                f"Discovered {len(ingestion.graph.resources)} resources. "
                "POST /api/v1/analyze with this data to get a migration plan."
            ),
            # Handed back so a caller (e.g. the dashboard's Discover tab) can
            # POST this straight to /api/v1/analyze as a file, without a
            # second live AWS CLI round-trip just to re-fetch what we already
            # have in hand.
            "raw_data": combined,
        }
    finally:
        tmp_path.unlink(missing_ok=True)


@app.get("/api/v1/discover/gcp")
def discover_gcp(project_id: str, region: str = "us-central1") -> dict[str, Any]:
    """Live GCP discovery via `gcloud compute instances list`. See
    discover_aws's docstring for why this is a plain `def`.
    """
    result = _run_cli(
        ["gcloud", "compute", "instances", "list", "--project", project_id, "--format", "json"]
    )
    if result.returncode != 0:
        raise HTTPException(status_code=400, detail=f"gcloud CLI failed: {result.stderr[:200]}")

    instances = json.loads(result.stdout)
    with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False, encoding="utf-8") as f:
        json.dump(instances, f)
        tmp_path = Path(f.name)

    try:
        ingestion = IngestionPipeline(settings=get_settings()).run(tmp_path)
        return {
            "project_id": project_id,
            "region": region,
            "resources_discovered": len(ingestion.graph.resources),
            "resource_types": sorted({r.source_type for r in ingestion.graph.resources.values()}),
            "raw_data": instances,
        }
    finally:
        tmp_path.unlink(missing_ok=True)


@app.get("/api/v1/health")
def health() -> dict[str, Any]:
    # Static build metadata — update alongside the actual test/engine counts.
    return {
        "status": "ok",
        "version": "2.0.3",
        "engines": 28,
        "supported_sources": ["aws", "gcp"],
        "supported_targets": ["gcp", "aws"],
        "parsers": 10,
        "tests_passing": 381,
    }
