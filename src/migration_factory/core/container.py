"""Dependency Injection container.

Deliberately a small, explicit registry rather than a decorator-magic
framework (e.g. `dependency-injector`, `punq`). Rationale, since this is a
real architectural choice and not an oversight:

  * Every wiring decision is visible in one place (`bootstrap.py`, added in
    Phase 1 delivery) instead of scattered across `@inject` decorators.
  * Zero runtime reflection/bytecode magic — easier to reason about, easier
    to unit test (swap a singleton for a fake with one line), zero surprise
    behavior under `mypy --strict`.
  * If the platform's composition root grows past what this comfortably
    supports, swapping to `dependency-injector` is a contained, mechanical
    change confined to this file — nothing above the container layer needs
    to know which implementation is in use.

Supports two lifetimes: singleton (one instance, built lazily on first
resolve) and factory (new instance every resolve).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

from migration_factory.core.exceptions import ConfigurationError

T = TypeVar("T")


@dataclass(slots=True)
class _Registration:
    factory: Callable[[], Any]
    singleton: bool
    instance: Any = None
    built: bool = False


@dataclass(slots=True)
class Container:
    _registrations: dict[type[Any], _Registration] = field(default_factory=dict)

    def register_singleton(self, interface: type[T], factory: Callable[[], T]) -> None:
        self._registrations[interface] = _Registration(factory=factory, singleton=True)

    def register_factory(self, interface: type[T], factory: Callable[[], T]) -> None:
        self._registrations[interface] = _Registration(factory=factory, singleton=False)

    def register_instance(self, interface: type[T], instance: T) -> None:
        self._registrations[interface] = _Registration(
            factory=lambda: instance, singleton=True, instance=instance, built=True
        )

    def resolve(self, interface: type[T]) -> T:
        registration = self._registrations.get(interface)
        if registration is None:
            raise ConfigurationError(
                f"No registration found for {interface!r}",
                context={"interface": getattr(interface, "__name__", str(interface))},
                remediation="Register it in the composition root before resolving, e.g. "
                "container.register_singleton(MyInterface, MyImplementation).",
            )
        if registration.singleton:
            if not registration.built:
                registration.instance = registration.factory()
                registration.built = True
            return registration.instance  # type: ignore[no-any-return]
        return registration.factory()  # type: ignore[no-any-return]

    def has(self, interface: type[Any]) -> bool:
        return interface in self._registrations
