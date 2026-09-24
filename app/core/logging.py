"""Structured logging configuration for CEKP."""

import json
import logging
import sys
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    """Format log records as JSON."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        for field in (
            "request_id",
            "method",
            "path",
            "status_code",
            "duration_ms",
        ):
            if hasattr(record, field):
                log_entry[field] = getattr(record, field)

        return json.dumps(log_entry)


def configure_logging() -> None:
    """Configure application-wide JSON logging."""

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)