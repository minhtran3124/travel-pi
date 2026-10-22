"""Logging configuration: one console handler and format for the whole process (app loggers and Uvicorn's)."""

from logging.config import dictConfig

from app.core.config import Settings


def configure_logging(settings: Settings) -> None:
    """Configure process-wide logging from ``settings`` (one console handler; ``uvicorn.access`` silenced since the request-logging middleware is the single source of per-request lines)."""
    dictConfig(
        {
            "version": 1,
            # Keep loggers created at import time (before this runs) working.
            "disable_existing_loggers": False,
            "formatters": {
                "standard": {
                    "format": "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
                    "datefmt": "%Y-%m-%d %H:%M:%S",
                },
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "standard",
                },
            },
            "root": {
                "level": settings.log_level.upper(),
                "handlers": ["console"],
            },
            "loggers": {
                "uvicorn": {"handlers": [], "propagate": True},
                "uvicorn.error": {"handlers": [], "propagate": True},
                "uvicorn.access": {"handlers": [], "propagate": False},
            },
        }
    )
