from __future__ import annotations

import pytest

from migration_factory.core.container import Container
from migration_factory.core.exceptions import ConfigurationError


class _Interface:
    def value(self) -> str:
        raise NotImplementedError


class _Impl(_Interface):
    def value(self) -> str:
        return "impl"


def test_resolve_unregistered_interface_raises_configuration_error() -> None:
    container = Container()
    with pytest.raises(ConfigurationError, match="No registration found"):
        container.resolve(_Interface)


def test_singleton_returns_same_instance_across_resolves() -> None:
    container = Container()
    build_count = 0

    def factory() -> _Impl:
        nonlocal build_count
        build_count += 1
        return _Impl()

    container.register_singleton(_Interface, factory)

    first = container.resolve(_Interface)
    second = container.resolve(_Interface)

    assert first is second
    assert build_count == 1  # built lazily, once


def test_factory_returns_new_instance_each_resolve() -> None:
    container = Container()
    container.register_factory(_Interface, _Impl)

    first = container.resolve(_Interface)
    second = container.resolve(_Interface)

    assert first is not second
    assert isinstance(first, _Impl)


def test_register_instance_returns_the_exact_object() -> None:
    container = Container()
    instance = _Impl()
    container.register_instance(_Interface, instance)

    assert container.resolve(_Interface) is instance


def test_has_reflects_registration_state() -> None:
    container = Container()
    assert container.has(_Interface) is False
    container.register_factory(_Interface, _Impl)
    assert container.has(_Interface) is True


def test_singleton_is_not_built_until_first_resolve() -> None:
    container = Container()
    built = False

    def factory() -> _Impl:
        nonlocal built
        built = True
        return _Impl()

    container.register_singleton(_Interface, factory)
    assert built is False  # registration alone must not trigger construction

    container.resolve(_Interface)
    assert built is True
