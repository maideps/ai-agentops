"""Structured JSON logging for the ``agentops`` logger namespace.

Only explicitly passed ``fields`` are logged; nothing reads or dumps the environment.
"""

import json
import logging
import sys
from datetime import UTC, datetime
from typing import TextIO

ROOT_LOGGER = "agentops"


class JsonFormatter(logging.Formatter):
    """Format each record as one JSON object; extra data goes in ``record.fields``."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            payload.update(fields)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO", stream: TextIO | None = None) -> None:
    """Send ``agentops.*`` logs as JSON to ``stream`` (default stderr), replacing old handlers."""
    logger = logging.getLogger(ROOT_LOGGER)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    handler = logging.StreamHandler(stream if stream is not None else sys.stderr)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
