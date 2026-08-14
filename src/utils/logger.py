"""
src/utils/logger.py
───────────────────
Structured logging setup using Python's standard logging module
with JSON formatting for production and a rich console formatter for dev.
"""
from __future__ import annotations

import logging
import logging.config
import os
from pathlib import Path
from typing import Any

import yaml


_LOGGING_CONFIGURED = False


def configure_logging(config_path: str | Path | None = None) -> None:
    """Configure application logging from YAML config file."""
    global _LOGGING_CONFIGURED
    if _LOGGING_CONFIGURED:
        return

    # Ensure logs directory exists
    Path("logs").mkdir(exist_ok=True)

    if config_path is None:
        config_path = Path(__file__).parent.parent.parent / "configs" / "logging.yaml"

    config_path = Path(config_path)
    if config_path.exists():
        with open(config_path) as f:
            config = yaml.safe_load(f)
        try:
            logging.config.dictConfig(config)
        except Exception:
            # Fallback to basic config if YAML parsing fails
            _configure_basic_logging()
    else:
        _configure_basic_logging()

    _LOGGING_CONFIGURED = True


def _configure_basic_logging() -> None:
    """Minimal fallback logging configuration."""
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d - %(message)s",
        datefmt="%H:%M:%S",
    )


def get_logger(name: str) -> logging.Logger:
    """
    Return a logger for the given module name.
    Automatically configures logging on first call.
    """
    configure_logging()
    return logging.getLogger(name)


class StructuredAdapter(logging.LoggerAdapter):
    """
    Logger adapter that merges extra fields into all log records,
    making it easy to attach contextual metadata (user_id, session_id, etc.)
    to every log line from a given scope.
    """

    def __init__(self, logger: logging.Logger, context: dict[str, Any]) -> None:
        super().__init__(logger, context)

    def process(self, msg: str, kwargs: dict) -> tuple[str, dict]:
        extra = kwargs.get("extra", {})
        extra.update(self.extra)
        kwargs["extra"] = extra
        return msg, kwargs


def get_request_logger(name: str, user_id: str, session_id: str) -> StructuredAdapter:
    """Create a logger pre-loaded with request context."""
    base_logger = get_logger(name)
    return StructuredAdapter(base_logger, {"user_id": user_id, "session_id": session_id})
