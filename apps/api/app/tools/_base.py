"""Shared helpers for service-wrapping tools that run inside the agent graph."""

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

# Params carrying personal data, redacted from logs as a backstop even if a tool passes locals() wholesale.
_REDACTED_PARAM_KEYS = {"preferences"}


def tool_error(e: AppError) -> ToolException:
    """Fold an ``AppError`` into a ``ToolException``, appending ``hint`` which ``str(e)`` drops."""
    message = str(e) if e.hint is None else f"{e.detail} Hint: {e.hint}"
    return ToolException(message)


def log_tool_call(name: str, params: dict[str, Any]) -> None:
    """Log a tool invocation and its parameter values as a scannable multi-line block."""
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
    """Normalise a service result into JSON-able data for tool output."""
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
    if isinstance(obj, list):
        return [dump(x) for x in obj]
    return obj


def panel_result(summary: str, *, kind: str, data: Any) -> tuple[str, dict]:
    """Build the ``(summary, artifact)`` return for a ``content_and_artifact`` panel tool.

    Raises ``UnknownPanelKind`` (deliberately not ``ValueError``, which panel tools wrap into a
    recoverable ``ToolException``) so a typo'd kind fails loudly instead of reaching the traveller.
    """
    if get_panel(kind) is None:
        raise UnknownPanelKind(f"unknown panel kind: {kind!r}")
    return summary, {"kind": kind, "data": dump(data)}
