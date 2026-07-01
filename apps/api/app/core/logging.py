"""Logging configuration.

A single ``dictConfig`` call wires up one console handler with a consistent
format for the whole process — the application's own loggers *and* Uvicorn's.
Call :func:`configure_logging` once on startup; every other module then just
does ``logger = logging.getLogger(__name__)`` and logs.
"""

from logging.config import dictConfig

from app.core.config import Settings


def configure_logging(settings: Settings) -> None:
    """Configure process-wide logging from ``settings``.

    - One console handler and one format, shared by the app and Uvicorn.
    - Uvicorn's own handlers are cleared so its records flow through ours
      instead of being formatted differently.
    - ``uvicorn.access`` is silenced on purpose: the request-logging
      middleware in ``app.main`` is the single source of per-request lines,
      so Uvicorn's access log would just be a duplicate.

    :param settings: Application settings, used to set the root log level.
    """
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
