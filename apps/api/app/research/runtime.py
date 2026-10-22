"""Process-level holder for the built research agent and its progress bus.

The chat graph is built at lifespan startup by ``build_graph`` **before** the
research agent exists, so the ``research`` chat node cannot capture the agent at
build time (``app/agents/graph.py``). Lifespan populates this holder right after it
builds ``app.state.research_agent`` / ``app.state.research_bus``, and
``build_research_service`` reads it — so the chat node and the REST routes drive
**one** agent through **one** bus. When research is off or the build failed the
holder stays ``(None, None)`` and the node declines instead of booking a run that
nothing can execute.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

    from app.research.progress import ProgressBus

_agent: CompiledStateGraph | None = None
_bus: ProgressBus | None = None


def set_research_runtime(
    agent: CompiledStateGraph | None,
    bus: ProgressBus | None,
) -> None:
    """Publish the built research agent + bus for the chat node to share."""
    global _agent, _bus
    _agent = agent
    _bus = bus


def get_research_runtime() -> tuple[CompiledStateGraph | None, ProgressBus | None]:
    """The shared ``(agent, bus)``; ``(None, None)`` until lifespan builds them."""
    return _agent, _bus
