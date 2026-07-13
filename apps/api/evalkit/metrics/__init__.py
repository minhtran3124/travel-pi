"""Registered eval metrics.

Importing this package runs each metric module's `register_metric(...)`
calls, populating `evalkit.registry`'s lookup table. See
`evalkit/metrics/deterministic.py` for the judge-free layer.
"""

from __future__ import annotations

import logging

from . import deterministic  # noqa: F401

logger = logging.getLogger(__name__)

# The judge-free layer above needs pydantic only. These two need optional extras
# (`agentevals`, `deepeval`); when an extra is absent the engine still runs — the
# affected metrics are simply not registered, and the runner reports them as
# unavailable rather than the whole import failing.
try:
    from . import trajectory  # noqa: F401
except ImportError:  # pragma: no cover - exercised only without the extra
    logger.warning("[EVALKIT] agentevals missing — trajectory metrics unavailable")

try:
    from . import judged  # noqa: F401
except ImportError:  # pragma: no cover - exercised only without the extra
    logger.warning("[EVALKIT] deepeval missing — judged (G-Eval) metrics unavailable")
