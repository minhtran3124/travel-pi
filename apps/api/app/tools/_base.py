"""Shared helpers for service-wrapping tools (specs/travel-agent Phase 3).

Tools run inside the agent graph, not a FastAPI request, so they can't use the
request-scoped ``get_session`` dependency. ``session_scope()`` opens a
short-lived session from the same factory (commit on success, rollback on
error), mirroring the unit-of-work the request boundary provides. ``dump()``
normalises Pydantic results to plain JSON-able structures so tool outputs are
always serialisable into the graph state / checkpoint.

Domain exceptions raised by services are mapped to ``ToolException`` via
:func:`tool_error`, which LangGraph's ``ToolNode`` surfaces back to the model as
a ``ToolMessage(status="error")`` so it can self-correct. Tools must go through
``tool_error`` rather than ``ToolException(str(e))`` directly: ``AppError.__str__``
returns ``detail`` only, so a bare ``str(e)`` silently drops ``hint`` — the
recovery pointer the model needs — even though it is written for exactly this
path.
"""

from __future__ import annotations

import logging
import pprint
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from langchain_core.tools import ToolException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.engine import get_session_factory
from app.exceptions import AppError
from app.streaming.panels import UnknownPanelKind, get_panel

logger = logging.getLogger("app.tools")

# Injected/free-text params that carry personal data and must never be
# rendered into logs, even when a tool passes `locals()` wholesale. Callers
# should still prefer excluding injected plumbing from `params` themselves
# (see the docstring below) — this is a backstop, not a substitute.
_REDACTED_PARAM_KEYS = {"preferences"}


def tool_error(e: AppError) -> ToolException:
    """Fold an ``AppError`` into a ``ToolException`` the model can act on.

    ``AppError.__str__`` returns ``detail`` only, so a bare
    ``ToolException(str(e))`` silently drops ``hint`` — the recovery pointer
    written specifically to help the agent self-correct. This appends it when
    present; with no ``hint`` the result is identical to ``str(e)``, so
    hint-less errors are unaffected.

    Call as ``raise tool_error(e) from e`` — the explicit ``from e`` preserves
    ``__cause__`` (this function does not set it itself, since the
    ``ToolException`` it returns is not yet raised).

    :param e: The caught domain error.
    :return: A ``ToolException`` ready to be raised.
    """
    message = str(e) if e.hint is None else f"{e.detail} Hint: {e.hint}"
    return ToolException(message)


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
    safe_params = {
        k: ("<redacted>" if k in _REDACTED_PARAM_KEYS else v) for k, v in params.items()
    }
    width = max(len(k) for k in safe_params)
    lines = [
        f"  {k:<{width}} = {pprint.pformat(v, width=80)}"
        for k, v in safe_params.items()
    ]
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
    :param kind: Panel kind identifier used by the FE to pick a renderer. Must be
        a kind registered in :mod:`app.streaming.panels` (see ``panel_kinds()``).
    :param data: Raw result data, JSON-normalised via :func:`dump` before being
        embedded in the artifact.
    :return: A ``(summary, artifact)`` tuple in the LangChain
        ``content_and_artifact`` shape.
    :raises UnknownPanelKind: If ``kind`` is not a registered panel kind — a typo'd
        kind is a programming error at the tool seam, not a runtime condition to
        swallow or fall back on. It is deliberately not a ``ValueError``: several
        panel tools wrap ``ValueError``/``AppError`` into ``ToolException``, which
        the agent relays back to the model as a recoverable logic error, so a bad
        kind would reach the traveller as a chat message instead of failing loudly.
    """
    if get_panel(kind) is None:
        raise UnknownPanelKind(f"unknown panel kind: {kind!r}")
    return summary, {"kind": kind, "data": dump(data)}
