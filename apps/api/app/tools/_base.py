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

import logging
import pprint
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.engine import get_session_factory

logger = logging.getLogger("app.tools")


def log_tool_call(name: str, params: dict[str, Any]) -> None:
    """Log that a tool is being called, with its parameter values.

    Called as the first statement of a ``@tool`` function so every tool
    invocation is traceable in the logs (which tool ran, with what args) —
    mirroring the agent-layer ``[agent] node=...`` INFO logs.

    Renders a pretty, multi-line block so multi-arg tools (e.g. ``book_hotel``
    with 11 params) are scannable instead of one long line:

    ::

        [tool] search_flights called
          origin          = 'HAN'
          destination     = 'SGN'
          departure_date  = '2027-03-15'
          airline         = None
          max_price       = None
          max_stops       = None
          sort            = 'departure_asc'

    :param name: The tool's name (function name).
    :param params: The tool's parameter values (typically ``locals()`` at the
        top of the function, excluding injected plumbing objects).
    """
    if not params:
        logger.info("[tool] %s called (no params)", name)
        return
    width = max(len(k) for k in params)
    lines = [f"  {k:<{width}} = {pprint.pformat(v, width=80)}" for k, v in params.items()]
    logger.info("[tool] %s called\n%s", name, "\n".join(lines))


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
    """Normalise a service result into JSON-able data for tool output.

    :param obj: The value to normalise (a Pydantic model, list, or plain value).
    :return: JSON-able data — model dumped, list recursed, other values unchanged.
    """
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

    :param summary: Concise text shown to the model.
    :param kind: Panel kind identifier used by the FE to pick a renderer.
    :param data: Raw result data, JSON-normalised via :func:`dump` before being
        embedded in the artifact.
    :return: A ``(summary, artifact)`` tuple in the LangChain
        ``content_and_artifact`` shape.
    """
    return summary, {"kind": kind, "data": dump(data)}
