"""Structured logging configuration using structlog.

Call ``configure_logging()`` once at application startup.  After that, use
``structlog.get_logger()`` anywhere in the codebase.
"""

import logging
import sys

import structlog


def configure_logging(log_level: str = "INFO") -> None:
    """Set up structlog with JSON output suitable for log aggregation (e.g.
    Elastic/Loki) and a human-friendly renderer in development."""

    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    structlog.configure(
        processors=shared_processors
        + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(),
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level.upper())

    for noisy in ("uvicorn.access", "openstack", "keystoneauth"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
