"""evalkit — a portable agent-eval engine.

Zero imports of this repo's `app.*`, and no fastapi/sqlalchemy/langgraph
dependency. Project-specific behaviour enters through the ports in
`evalkit.ports` (`AgentRunner`, `Oracle`, `Metric`, `DatasetStore`,
`BaselineStore`), implemented by an adapter living outside this package.
See `specs/agent-eval-pipeline/design-portability.md` for the full design.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"
