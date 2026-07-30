"""Structured JSON logging.

Emits one JSON object per log line so logs are queryable in CloudWatch Logs
Insights (and any other log aggregator). A per-request correlation id is
carried through a ``ContextVar`` and attached to every record automatically.
"""

from __future__ import annotations

import contextvars
import datetime as dt
import json
import logging
import sys
from typing import Any

# Correlation id for the in-flight request; set by middleware, read by the
# formatter. Defaults to "-" for logs emitted outside a request (startup, etc.).
request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

# Standard LogRecord attributes we don't want to duplicate into the JSON "extra".
_RESERVED_ATTRS = {
    "args", "asctime", "created", "exc_info", "exc_text", "filename",
    "funcName", "levelname", "levelno", "lineno", "module", "msecs",
    "message", "msg", "name", "pathname", "process", "processName",
    "relativeCreated", "stack_info", "thread", "threadName", "taskName",
}


class JsonFormatter(logging.Formatter):
    """Format log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": dt.datetime.fromtimestamp(record.created, tz=dt.timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_ctx.get(),
        }

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)

        # Merge any structured fields passed via `logger.info(..., extra={...})`.
        for key, value in record.__dict__.items():
            if key not in _RESERVED_ATTRS and not key.startswith("_"):
                payload.setdefault(key, value)

        return json.dumps(payload, default=str)


class PlainFormatter(logging.Formatter):
    """Human-friendly formatter for local development (LOG_JSON=false)."""

    def format(self, record: logging.LogRecord) -> str:
        rid = request_id_ctx.get()
        base = f"{self.formatTime(record)} {record.levelname:<8} [{rid}] {record.name}: {record.getMessage()}"
        if record.exc_info:
            base = f"{base}\n{self.formatException(record.exc_info)}"
        return base


def setup_logging(level: str = "INFO", json_output: bool = True) -> None:
    """Configure root logging and align uvicorn/gunicorn loggers to our format."""
    formatter: logging.Formatter = JsonFormatter() if json_output else PlainFormatter()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())

    # Route the servers' loggers through our handler and stop double logging.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "gunicorn.error", "gunicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True

    # The request middleware already emits a structured access log per request,
    # so silence the servers' duplicate per-request access logs.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("gunicorn.access").setLevel(logging.WARNING)

    # Neo4j emits INFORMATION-level notifications (e.g. "constraint already
    # exists" from idempotent schema application); keep only warnings+.
    logging.getLogger("neo4j.notifications").setLevel(logging.WARNING)
