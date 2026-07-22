"""Mapper / Normalizer layer — the second pipeline stage:
`ParsedResource` (provider-native) -> `CanonicalResource` (normalized).

A mapper is registered against specific `source_type` strings (e.g.
`aws_instance`). Unlike parsers (one per input *format*), mappers are one per
input *provider* and are consulted per-resource-type, so a single
`AWSToCanonicalMapper` handles many `aws_*` types internally via its own
dispatch table — see `mappers/aws_to_canonical.py`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from migration_factory.domain.canonical_model import CanonicalResource
from migration_factory.parsers.base import ParsedResource


class BaseMapper(ABC):
    name: str

    @abstractmethod
    def supports(self, source_type: str) -> bool:
        """Cheap, side-effect-free check: can this mapper normalize this
        provider-native resource type? Must not raise.
        """
        raise NotImplementedError

    @abstractmethod
    def map(self, parsed: ParsedResource) -> CanonicalResource:
        """Normalize one `ParsedResource` into a `CanonicalResource`.

        Must raise `migration_factory.core.exceptions.MappingError` (not a
        bare exception) when `parsed.source_type` is not actually supported —
        callers are expected to have checked `supports()` first, but mappers
        must fail safely regardless of caller discipline.
        """
        raise NotImplementedError
