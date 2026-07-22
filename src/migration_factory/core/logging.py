"""Structured logging.

Every log line is a JSON object (in prod) carrying `trace_id` and
`execution_id` so a single migration run can be reconstructed end-to-end
across parsers, mappers, and (in later phases) the AI/Terraform/Deployment
engines — this is the backbone that AIOps log-correlation and root-cause
analysis will consume later. Console format is available for local dev.
"""

from __future__ import annotations

import contextvars
import logging
import sys
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, cast

import structlog

from migration_factory.core.config import LogFormat, Settings

_trace_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "trace_id", default=None
)
_execution_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "execution_id", default=None
)


def _inject_context_ids(
    logger: Any, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    trace_id = _trace_id_var.get()
    execution_id = _execution_id_var.get()
    if trace_id:
        event_dict["trace_id"] = trace_id
    if execution_id:
        event_dict["execution_id"] = execution_id
    return event_dict


def configure_logging(settings: Settings) -> None:
    """Call once at process startup (CLI entrypoint / service bootstrap).

    Logs go to stderr, never stdout. Every command in this CLI writes its
    actual output (reports, generated artifacts) to stdout so it can be
    piped into `jq`, redirected to a file, or consumed by another program —
    log noise on stdout would silently corrupt that contract.
    """
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stderr,
        level=settings.logging.level,
        force=True,
    )

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        _inject_context_ids,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    renderer: Any = (
        structlog.processors.JSONRenderer()
        if settings.logging.format is LogFormat.JSON
        else structlog.dev.ConsoleRenderer()
    )

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(settings.logging.level)
        ),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return cast("structlog.stdlib.BoundLogger", structlog.get_logger(name))


@contextmanager
def execution_context(*, execution_id: str | None = None) -> Iterator[str]:
    """Bind a trace_id + execution_id for the duration of a migration run
    (or any unit of work). Every log line emitted within this context —
    across every module, no manual passing of IDs required — carries both.

    Example:
        with execution_context() as trace_id:
            logger.info("run_started")
            parser.parse(...)   # logs from here inherit the same trace_id
    """
    trace_id = str(uuid.uuid4())
    exec_id = execution_id or str(uuid.uuid4())

    trace_token = _trace_id_var.set(trace_id)
    exec_token = _execution_id_var.set(exec_id)
    try:
        yield trace_id
    finally:
        _trace_id_var.reset(trace_token)
        _execution_id_var.reset(exec_token)
