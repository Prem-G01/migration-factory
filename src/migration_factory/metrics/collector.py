"""Metrics Collection.

OpenTelemetry-compatible metrics interface with an in-memory collector
for environments without an OTLP endpoint. Production: configure the
OTLP exporter. Development: metrics accumulate in memory and are
queryable via `collector.get_metrics()`.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from migration_factory.core.logging import get_logger

logger = get_logger(__name__)


class MetricPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    value: float
    labels: dict[str, str] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class MetricsSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    total_metrics: int = 0
    counters: dict[str, float] = Field(default_factory=dict)
    gauges: dict[str, float] = Field(default_factory=dict)
    histograms: dict[str, list[float]] = Field(default_factory=dict)


@dataclass(slots=True)
class MetricsCollector:
    """In-memory metrics collector. Drop-in replacement for OTLP exporter."""

    _counters: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    _gauges: dict[str, float] = field(default_factory=dict)
    _histograms: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))
    _points: list[MetricPoint] = field(default_factory=list)

    def increment(self, name: str, value: float = 1.0, **labels: str) -> None:
        self._counters[name] += value
        self._points.append(MetricPoint(name=name, value=value, labels=labels))

    def gauge(self, name: str, value: float, **labels: str) -> None:
        self._gauges[name] = value
        self._points.append(MetricPoint(name=name, value=value, labels=labels))

    def histogram(self, name: str, value: float, **labels: str) -> None:
        self._histograms[name].append(value)
        self._points.append(MetricPoint(name=name, value=value, labels=labels))

    def get_summary(self) -> MetricsSummary:
        return MetricsSummary(
            total_metrics=len(self._points),
            counters=dict(self._counters),
            gauges=dict(self._gauges),
            histograms=dict(self._histograms),
        )

    def reset(self) -> None:
        self._counters.clear()
        self._gauges.clear()
        self._histograms.clear()
        self._points.clear()


# Global collector instance
_collector: MetricsCollector | None = None


def get_metrics_collector() -> MetricsCollector:
    global _collector
    if _collector is None:
        _collector = MetricsCollector()
    return _collector
