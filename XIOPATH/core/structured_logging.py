"""
XIOPATH — Structured Logging (Phase S.3)
==========================================
JSON-formatted structured logging with correlation IDs, agent context,
and per-module log level configuration.

Usage:
    from core.structured_logging import configure_logging, get_logger

    # Call once at startup
    configure_logging()

    # Use in modules
    logger = get_logger("MyModule")
    logger.info("action_completed", action="navigate", duration_ms=123, url="https://...")
"""

import os
import sys
import logging
import structlog
from typing import Optional


def configure_logging(
    default_level: str = "INFO",
    json_output: bool = True,
):
    """
    Configure structured logging for the entire application.

    Args:
        default_level: Default log level (overridden by XIOPATH_LOG_LEVEL env var)
        json_output: If True, output JSON. If False, output human-readable (dev mode).

    Environment variables:
        XIOPATH_LOG_LEVEL: Override default log level (e.g., "DEBUG")
        XIOPATH_LOG_LEVELS: Per-module overrides (e.g., "API_MAIN=DEBUG,AgentLoop=WARNING")
        XIOPATH_LOG_FORMAT: "json" or "console" (overrides json_output)
    """
    # Determine output format
    fmt = os.environ.get("XIOPATH_LOG_FORMAT", "json" if json_output else "console")
    level_name = os.environ.get("XIOPATH_LOG_LEVEL", default_level).upper()
    level = getattr(logging, level_name, logging.INFO)

    # Apply per-module log levels
    module_levels = os.environ.get("XIOPATH_LOG_LEVELS", "")
    if module_levels:
        for pair in module_levels.split(","):
            pair = pair.strip()
            if "=" in pair:
                mod, lvl = pair.split("=", 1)
                mod_level = getattr(logging, lvl.upper(), None)
                if mod_level is not None:
                    logging.getLogger(mod.strip()).setLevel(mod_level)

    # Shared processors for both structlog and stdlib
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if fmt == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    # Configure structlog
    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configure stdlib logging to use structlog formatter
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    # Reset root logger
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)

    # Quiet noisy libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """
    Get a structured logger bound with the module name.

    Usage:
        logger = get_logger("AgentLoop")
        logger.info("step_completed", action="click", duration_ms=45)
    """
    return structlog.get_logger(name)


def bind_context(**kwargs):
    """
    Bind key-value pairs to the current context (e.g., request_id, agent_id).
    These will appear in all subsequent log entries within the same context.

    Usage:
        bind_context(request_id="abc-123", agent_id="agent_colab_1")
    """
    structlog.contextvars.bind_contextvars(**kwargs)


def clear_context():
    """Clear all bound context variables."""
    structlog.contextvars.clear_contextvars()
