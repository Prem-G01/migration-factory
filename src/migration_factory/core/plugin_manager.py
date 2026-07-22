"""Plugin Manager.

Parsers and mappers are discovered via Python packaging entry points
(`importlib.metadata`), not hardcoded imports. This is what makes "add a new
input format" or "add a new resource mapping" a packaging-level change
(register an entry point, ship a wheel) instead of a change to core code —
the literal definition of the "zero hardcoding / plugin based" requirement.

A third-party package can ship its own parser and register it under the
`migration_factory.parsers` group without ever touching this repository.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib.metadata import EntryPoint, entry_points
from typing import Generic, TypeVar

from migration_factory.core.exceptions import PluginError
from migration_factory.core.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


@dataclass(slots=True)
class LoadedPlugin(Generic[T]):
    name: str
    plugin_class: type[T]
    entry_point: EntryPoint


@dataclass(slots=True)
class PluginManager(Generic[T]):
    """Generic plugin loader for a single entry-point group.

    Usage:
        parser_plugins = PluginManager[BaseParser](group="migration_factory.parsers")
        parser_plugins.load()
        for plugin in parser_plugins.plugins.values():
            instance = plugin.plugin_class()
    """

    group: str
    fail_fast: bool = False
    plugins: dict[str, LoadedPlugin[T]] = field(default_factory=dict)
    load_errors: dict[str, str] = field(default_factory=dict)

    def load(self) -> None:
        """Discover and import every entry point registered in `self.group`.

        Failures are isolated per-plugin: a single broken plugin cannot take
        down platform startup unless `fail_fast=True` — critical for a
        platform that will accumulate dozens of third-party format plugins
        over time.
        """
        discovered = entry_points(group=self.group)
        logger.info("plugin_discovery_started", group=self.group, count=len(discovered))

        for ep in discovered:
            try:
                plugin_class = ep.load()
            except Exception as exc:  # noqa: BLE001 — intentionally broad: isolate any plugin failure
                self.load_errors[ep.name] = str(exc)
                logger.error(
                    "plugin_load_failed",
                    group=self.group,
                    plugin_name=ep.name,
                    error=str(exc),
                )
                if self.fail_fast:
                    raise PluginError(
                        f"Failed to load plugin {ep.name!r} in group {self.group!r}",
                        context={"group": self.group, "plugin_name": ep.name},
                        remediation="Fix the plugin's import path or dependencies, "
                        "or set fail_fast_on_load_error=False to skip it.",
                        cause=exc,
                    ) from exc
                continue

            self.plugins[ep.name] = LoadedPlugin(
                name=ep.name, plugin_class=plugin_class, entry_point=ep
            )
            logger.info("plugin_loaded", group=self.group, plugin_name=ep.name)

    def get(self, name: str) -> type[T]:
        try:
            return self.plugins[name].plugin_class
        except KeyError as exc:
            raise PluginError(
                f"No plugin named {name!r} registered in group {self.group!r}",
                context={"group": self.group, "requested": name, "available": list(self.plugins)},
                remediation="Check the plugin name or verify it is registered under "
                f"[project.entry-points.'{self.group}'] in pyproject.toml.",
            ) from exc

    def all_classes(self) -> list[type[T]]:
        return [p.plugin_class for p in self.plugins.values()]
