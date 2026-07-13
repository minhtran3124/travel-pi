"""Registered eval metrics.

Importing this package runs each metric module's `register_metric(...)`
calls, populating `evalkit.registry`'s lookup table. See
`evalkit/metrics/deterministic.py` for the judge-free layer.
"""

from __future__ import annotations

from . import deterministic  # noqa: F401
