"""Ingestion Pipeline — composition root for Phase 0 + Phase 1.

Wires: Parser Registry -> Mapper Registry -> Canonical Infrastructure Graph.
This module is intentionally thin; it contains orchestration only, no
business logic — parsing logic lives in parsers/, mapping logic in mappers/,
graph logic in domain/. That separation is what keeps each layer unit
testable without spinning up the others (see tests/unit/ vs tests/integration/).

Later phases (Dependency Engine, AI Engine, Security/FinOps/Compliance
Engines, Terraform Generator) extend this pipeline as additional stages
appended after `IngestionReport.graph` — never by reaching backward into
the parser/mapper layers.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from migration_factory.core.config import Settings, get_settings
from migration_factory.core.exceptions import MappingError, MigrationFactoryError
from migration_factory.core.logging import execution_context, get_logger
from migration_factory.core.plugin_manager import PluginManager
from migration_factory.domain.canonical_model import CanonicalInfrastructureGraph
from migration_factory.mappers.base import BaseMapper
from migration_factory.mappers.registry import MapperRegistry
from migration_factory.parsers.base import BaseParser, ParseWarning
from migration_factory.parsers.registry import ParserRegistry

logger = get_logger(__name__)


class IngestionReport(BaseModel):
    """Result of running the ingestion pipeline against one input file."""

    model_config = ConfigDict(extra="forbid")

    source_path: str
    parser_used: str
    graph: CanonicalInfrastructureGraph
    parse_warnings: list[ParseWarning] = Field(default_factory=list)
    unsupported_resources: list[str] = Field(
        default_factory=list, description="Terraform addresses with no registered mapper"
    )
    dangling_dependencies: list[str] = Field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return not (self.parse_warnings or self.unsupported_resources or self.dangling_dependencies)


class IngestionPipeline:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._parser_registry = ParserRegistry(
            plugin_manager=PluginManager[BaseParser](
                group=self.settings.plugins.parser_entrypoint_group,
                fail_fast=self.settings.plugins.fail_fast_on_load_error,
            )
        )
        self._mapper_registry = MapperRegistry(
            plugin_manager=PluginManager[BaseMapper](
                group=self.settings.plugins.mapper_entrypoint_group,
                fail_fast=self.settings.plugins.fail_fast_on_load_error,
            )
        )
        self._initialized = False

    def initialize(self) -> None:
        self._parser_registry.initialize()
        self._mapper_registry.initialize()
        self._initialized = True

    def run(self, source_path: Path) -> IngestionReport:
        if not self._initialized:
            self.initialize()

        with execution_context() as trace_id:
            logger.info("ingestion_started", source_path=str(source_path), trace_id=trace_id)

            parser = self._parser_registry.resolve(source_path)
            parse_result = parser.parse(source_path)

            graph = CanonicalInfrastructureGraph()
            unsupported: list[str] = []

            for parsed_resource in parse_result.resources:
                try:
                    mapper = self._mapper_registry.resolve(parsed_resource.source_type)
                    canonical_resource = mapper.map(parsed_resource)
                    graph.add_resource(canonical_resource)
                except MappingError as exc:
                    if self.settings.parsing.fail_on_unsupported_resource:
                        raise
                    unsupported.append(parsed_resource.source_identifier)
                    logger.warning(
                        "resource_unsupported_skipped",
                        source_identifier=parsed_resource.source_identifier,
                        source_type=parsed_resource.source_type,
                        error=exc.message,
                    )

            dangling = graph.validate_references()

            report = IngestionReport(
                source_path=str(source_path),
                parser_used=parser.name,
                graph=graph,
                parse_warnings=parse_result.warnings,
                unsupported_resources=unsupported,
                dangling_dependencies=dangling,
            )

            logger.info(
                "ingestion_completed",
                source_path=str(source_path),
                resources_mapped=len(graph.resources),
                unsupported_count=len(unsupported),
                warning_count=len(parse_result.warnings),
                dangling_dependency_count=len(dangling),
            )
            return report


__all__ = ["IngestionPipeline", "IngestionReport", "MigrationFactoryError"]
