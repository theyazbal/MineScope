"""Structured logging setup. Never logs secrets."""

from __future__ import annotations

import json
import logging
from typing import Any

_RESERVED = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    """Format log records as single-line JSON documents."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


def configure_logging(level: str = "WARNING", log_file: str | None = None,
                      structured: bool = False) -> logging.Logger:
    """Configure the ``minescope`` logger and return it."""
    logger = logging.getLogger("minescope")
    logger.setLevel(getattr(logging, level.upper(), logging.WARNING))
    for old in list(logger.handlers):
        logger.removeHandler(old)
        old.close()
    handler: logging.Handler = (
        logging.FileHandler(log_file, encoding="utf-8") if log_file else logging.StreamHandler()
    )
    handler.setFormatter(
        JsonFormatter() if structured
        else logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    logger.addHandler(handler)
    logger.propagate = False
    return logger
