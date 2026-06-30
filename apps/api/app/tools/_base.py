"""Shared helpers for service-wrapping tools (specs/travel-agent Phase 3).

Tools run inside the agent graph, not a FastAPI request, so they can't use the
request-scoped ``get_session`` dependency. ``session_scope()`` opens a
short-lived session from the same factory (commit on success, rollback on
error), mirroring the unit-of-work the request boundary provides. ``dump()``
normalises Pydantic results to plain JSON-able structures so tool outputs are
always serialisable into the graph state / checkpoint.

Domain exceptions raised by services are mapped to ``ToolException`` by the
individual tools, which LangGraph's ``ToolNode`` surfaces back to the model as a
``ToolMessage(status="error")`` so it can self-correct.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.engine import get_session_factory


@contextmanager
def session_scope() -> Iterator[Session]:
    """Yield a short-lived DB session for one tool call (commit/rollback/close)."""
    factory = get_session_factory(get_settings().database_url)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def dump(obj: Any) -> Any:
    """Normalise a service result into JSON-able data for tool output."""
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
    if isinstance(obj, list):
        return [dump(x) for x in obj]
    return obj


def panel_result(summary: str, *, kind: str, data: Any) -> tuple[str, dict]:
    """Return value for a ``@tool(response_format="content_and_artifact")`` panel tool.

    ``summary`` is the concise text the model sees; the artifact
    ``{"kind", "data"}`` is forwarded by the stream mapper as a ``panel`` SSE
    event to the FE side-panel drawer (specs/agent-side-panel) and is *not* sent
    to the model. ``data`` is JSON-normalised via :func:`dump`.
    """
    return summary, {"kind": kind, "data": dump(data)}
