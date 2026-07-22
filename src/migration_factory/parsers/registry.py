"""Parser Registry.

Wraps the generic `PluginManager` with parser-specific behavior: given a file,
find every registered parser willing to claim it (`supports()`), and fail
loudly on ambiguity rather than silently picking one — an input format that
two parsers both claim is a configuration bug that should surface at
discovery time, not produce nondeterministic output.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from migration_factory.core.exceptions import ParserError
from migration_factory.core.logging import get_logger
from migration_factory.core.plugin_manager import PluginManager
from migration_factory.parsers.base import BaseParser, ParserResult

logger = get_logger(__name__)


@dataclass(slots=True)
class ParserRegistry:
    plugin_manager: PluginManager[BaseParser]
    _instances: dict[str, BaseParser] = field(default_factory=dict)

    def initialize(self) -> None:
        self.plugin_manager.load()
        for name, loaded in self.plugin_manager.plugins.items():
            self._instances[name] = loaded.plugin_class()

    def resolve(self, source_path: Path) -> BaseParser:
        candidates = [p for p in self._instances.values() if p.supports(source_path)]

        if not candidates:
            raise ParserError(
                f"No registered parser supports {source_path}",
                context={
                    "source_path": str(source_path),
                    "available_parsers": list(self._instances),
                },
                remediation="Register a parser plugin that supports this file type, "
                "or verify the file extension/content matches an existing parser's "
                "`supports()` check.",
            )

        if len(candidates) > 1:
            raise ParserError(
                f"Ambiguous parser resolution for {source_path}: multiple parsers claim it",
                context={
                    "source_path": str(source_path),
                    "matching_parsers": [c.name for c in candidates],
                },
                remediation="Tighten `supports()` on the conflicting parsers so exactly "
                "one claims this input, or pass an explicit parser name.",
            )

        return candidates[0]

    def parse(self, source_path: Path) -> ParserResult:
        parser = self.resolve(source_path)
        logger.info("parser_resolved", parser=parser.name, source_path=str(source_path))
        return parser.parse(source_path)
