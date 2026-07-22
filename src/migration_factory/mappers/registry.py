"""Mapper Registry — mirrors `ParserRegistry`'s auto-detection pattern for
the normalization stage: given a `source_type`, find the mapper willing to
claim it, and fail loudly on ambiguity.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from migration_factory.core.exceptions import MappingError
from migration_factory.core.logging import get_logger
from migration_factory.core.plugin_manager import PluginManager
from migration_factory.mappers.base import BaseMapper

logger = get_logger(__name__)


@dataclass(slots=True)
class MapperRegistry:
    plugin_manager: PluginManager[BaseMapper]
    _instances: dict[str, BaseMapper] = field(default_factory=dict)

    def initialize(self) -> None:
        self.plugin_manager.load()
        for name, loaded in self.plugin_manager.plugins.items():
            self._instances[name] = loaded.plugin_class()

    def resolve(self, source_type: str) -> BaseMapper:
        candidates = [m for m in self._instances.values() if m.supports(source_type)]

        if not candidates:
            raise MappingError(
                f"No registered mapper supports resource type {source_type!r}",
                context={"source_type": source_type, "available_mappers": list(self._instances)},
                remediation="Register a mapper plugin covering this resource type.",
            )
        if len(candidates) > 1:
            raise MappingError(
                f"Ambiguous mapper resolution for {source_type!r}: multiple mappers claim it",
                context={
                    "source_type": source_type,
                    "matching_mappers": [c.name for c in candidates],
                },
                remediation="Tighten `supports()` on the conflicting mappers.",
            )
        return candidates[0]
