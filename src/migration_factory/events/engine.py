"""Event Bus and Notification Framework.

Simple in-process pub/sub for pipeline stage coordination and notification
dispatch. Each engine can publish events (pipeline_started, resource_parsed,
translation_completed, etc.) and handlers can subscribe to react.

In production, this would be backed by Redis Pub/Sub, Cloud Pub/Sub, or
an event stream — the interface is identical, only the transport changes.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from migration_factory.core.logging import get_logger

logger = get_logger(__name__)


class EventType(StrEnum):
    PIPELINE_STARTED = "pipeline.started"
    PIPELINE_COMPLETED = "pipeline.completed"
    PIPELINE_FAILED = "pipeline.failed"
    PARSING_STARTED = "parsing.started"
    PARSING_COMPLETED = "parsing.completed"
    TRANSLATION_COMPLETED = "translation.completed"
    ASSESSMENT_COMPLETED = "assessment.completed"
    VALIDATION_COMPLETED = "validation.completed"
    SECURITY_COMPLETED = "security.completed"
    COMPLIANCE_COMPLETED = "compliance.completed"
    TERRAFORM_GENERATED = "terraform.generated"
    MIGRATION_WAVE_STARTED = "migration.wave.started"
    MIGRATION_WAVE_COMPLETED = "migration.wave.completed"
    RESOURCE_MIGRATED = "resource.migrated"
    RESOURCE_FAILED = "resource.failed"
    ROLLBACK_INITIATED = "rollback.initiated"
    NOTIFICATION_SENT = "notification.sent"


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: EventType
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    data: dict[str, Any] = Field(default_factory=dict)
    source: str = ""
    trace_id: str = ""


class NotificationChannel(StrEnum):
    LOG = "log"
    WEBHOOK = "webhook"
    EMAIL = "email"
    SLACK = "slack"


class Notification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channel: NotificationChannel
    subject: str
    body: str
    metadata: dict[str, str] = Field(default_factory=dict)
    sent: bool = False


EventHandler = Any  # Callable[[Event], None]


@dataclass(slots=True)
class EventBus:
    """In-process pub/sub event bus."""

    _handlers: dict[EventType, list[Any]] = field(default_factory=lambda: defaultdict(list))
    _event_log: list[Event] = field(default_factory=list)

    def subscribe(self, event_type: EventType, handler: Any) -> None:
        self._handlers[event_type].append(handler)
        logger.debug("event_handler_subscribed", event_type=event_type.value)

    def publish(self, event: Event) -> None:
        self._event_log.append(event)
        logger.info("event_published", event_type=event.event_type.value, source=event.source)
        for handler in self._handlers.get(event.event_type, []):
            try:
                handler(event)
            except Exception as exc:
                logger.error("event_handler_failed", event_type=event.event_type.value, error=str(exc))

    @property
    def event_history(self) -> list[Event]:
        return list(self._event_log)

    def clear(self) -> None:
        self._event_log.clear()


@dataclass(slots=True)
class NotificationEngine:
    """Dispatches notifications via configured channels."""

    _sent: list[Notification] = field(default_factory=list)

    def notify(self, channel: NotificationChannel, subject: str, body: str, **metadata: str) -> Notification:
        notification = Notification(
            channel=channel,
            subject=subject,
            body=body,
            metadata=metadata,
        )

        if channel is NotificationChannel.LOG:
            logger.info("notification", subject=subject, body=body[:200])
            notification.sent = True
        elif channel is NotificationChannel.WEBHOOK:
            # Production: httpx.post(metadata["url"], json={...})
            logger.info("notification_webhook", subject=subject, url=metadata.get("url", ""))
            notification.sent = True
        else:
            logger.info("notification_queued", channel=channel.value, subject=subject)

        self._sent.append(notification)
        return notification

    @property
    def sent_notifications(self) -> list[Notification]:
        return list(self._sent)
