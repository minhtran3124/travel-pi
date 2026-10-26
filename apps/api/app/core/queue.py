"""Arq/Redis job queue seam (specs/prod-deploy-render-concurrency, Task 5).

The web process only *enqueues*; ``app/worker.py`` consumes. With ``REDIS_URL``
unset the queue is off and callers keep today's in-process behaviour. ``arq`` is
imported lazily so the zero-config path never needs a Redis client.

Idempotency: every job is enqueued under a caller-chosen ``job_id`` (the run id);
Arq refuses a second job with the same id while the first is queued or its result
is retained, so a duplicate enqueue is a no-op.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_pool: Any = None


def queue_enabled() -> bool:
    """True when ``REDIS_URL`` is set, i.e. background work goes to the worker."""
    return bool(get_settings().redis_url)


async def _get_pool() -> Any:
    global _pool
    if _pool is None:
        from arq import create_pool
        from arq.connections import RedisSettings

        _pool = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    return _pool


async def enqueue(function: str, *args: Any, job_id: str, **kwargs: Any) -> bool:
    """Enqueue ``function`` on the worker under ``job_id``.

    :return: ``True`` when queued, ``False`` when a job with this id already exists
        (idempotent duplicate). Raises if Redis is unreachable; callers decide
        whether to fall back.
    """
    pool = await _get_pool()
    job = await pool.enqueue_job(function, *args, _job_id=job_id, **kwargs)
    if job is None:
        logger.info("[queue] %s job_id=%s already queued; skipped", function, job_id)
        return False
    return True


async def close_pool() -> None:
    """Close the cached Redis pool (lifespan shutdown). Safe when never opened."""
    global _pool
    pool, _pool = _pool, None
    if pool is not None:
        await pool.aclose()
