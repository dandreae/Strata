"""Structured logging setup.

Uses the standard library `logging` module with an optional JSON formatter
so log lines are easy to read locally (plain text) and easy to ingest in
Cloud Logging when deployed to Cloud Run (JSON). No third-party logging
library is pulled in for this.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any


class JsonFormatter(logging.Formatter):
    """Renders log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        # Allow callers to attach structured context via `extra={"context": {...}}`.
        context = getattr(record, "context", None)
        if context:
            payload["context"] = context

        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO", json_output: bool = False) -> None:
    """Configure the root logger once, at process startup."""
    root = logging.getLogger()
    root.setLevel(level.upper())

    # Avoid duplicate handlers if configure_logging is called more than once
    # (e.g. under the test runner reloading the app).
    root.handlers.clear()

    handler = logging.StreamHandler(stream=sys.stdout)
    if json_output:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
                datefmt="%H:%M:%S",
            )
        )
    root.addHandler(handler)

    # Quiet down noisy third-party loggers unless we're debugging.
    if level.upper() != "DEBUG":
        logging.getLogger("uvicorn.access").setLevel("WARNING")


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
