"""Migration Factory — AI-Powered Multi-Cloud Infrastructure Migration Platform.

This package currently implements the Foundation layer (Phase 0) and the first
Ingestion vertical slice (Phase 1): Terraform State parsing -> AWS-to-Canonical
mapping -> Canonical Infrastructure Graph.

See ARCHITECTURE.md for the full pipeline and module roadmap.
"""

from migration_factory.core.exceptions import (
    ConfigurationError,
    MappingError,
    MigrationFactoryError,
    ParserError,
    PluginError,
)

__all__ = [
    "MigrationFactoryError",
    "ConfigurationError",
    "ParserError",
    "MappingError",
    "PluginError",
]

__version__ = "0.1.0"
