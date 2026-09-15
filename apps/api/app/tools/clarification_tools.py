"""Clarification signal tool (MIN-68, specs/min-68-ledger-early-exit).

Deliberately NOT registered in ``app.tools.registry``: it is graph
control-flow (the ``awaiting_user`` state signal consumed by reflection's
early-exit guard), not a domain capability — keeping it out of the registry
keeps it off the MCP server and
``/agent/manifest``, which are registry-driven. ``build_subagent``
(``app.agents.subagents._base``) appends it to every sub-agent's toolset.
"""

from __future__ import annotations

import logging
from typing import Annotated

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.types import Command

from app.schemas.base import AppBaseModel

logger = logging.getLogger(__name__)


class NeedsClarificationArgs(AppBaseModel):
    # No model-facing args. The injected id is declared (not omitted) so
    # ToolNode still injects it; it stays out of the model-facing schema.
    tool_call_id: Annotated[str, InjectedToolCallId]


@tool(args_schema=NeedsClarificationArgs)
def needs_clarification(
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Signal that you are blocked on the traveller and cannot proceed.

    Call this ONCE when you cannot complete the request without a detail
    only the traveller can provide (an exact date, a destination, a
    headcount) — then finish your reply by asking for exactly that missing
    detail. Any remaining queued work for this turn is cancelled; it will be
    re-planned after the traveller answers. Do NOT call this when a tool
    merely failed or returned nothing — report that honestly instead.

    :param tool_call_id: The originating tool call id, injected by LangGraph
        (not model-supplied) so the resulting ``ToolMessage`` pairs with
        this call.
    :return: A ``Command`` setting ``awaiting_user`` and emitting the paired
        ``ToolMessage``.
    """
    logger.info("[agent] tool=needs_clarification (blocked on traveller)")
    return Command(
        update={
            "awaiting_user": True,
            "messages": [
                ToolMessage(
                    content=(
                        "Understood — remaining queued work for this turn is "
                        "cancelled. Finish your reply by asking the traveller "
                        "for exactly the missing detail."
                    ),
                    tool_call_id=tool_call_id,
                )
            ],
        }
    )
