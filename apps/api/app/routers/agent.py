"""Agent endpoints — /agent/chat, /agent/stream, /agent/manifest.

specs/travel-agent Task 6.1. The compiled graph is resolved through
``get_travel_graph`` so tests swap in a FakeLLM-backed graph with one override.
Conversations/messages are persisted alongside the LangGraph checkpointer (which
owns the live thread state).
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.streaming import sse_response
from app.db.session import get_session
from app.exceptions import UpstreamError
from app.repositories.conversation import ConversationRepository
from app.routers.tags import Tags
from app.schemas.agent import (
    AgentManifest,
    ChatRequest,
    ChatResponse,
    ToolManifestEntry,
)
from app.schemas.error import error_responses
from app.tools.registry import ALL_TOOLS, TOOL_METADATA

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=[Tags.agent], responses=error_responses(422))


def get_travel_graph(request: Request) -> Any:
    """Return the shared compiled graph built once in ``lifespan`` (REVIEW.md C1).

    The graph + checkpointer + store are constructed a single time at startup and
    held on ``app.state``; resolving them here per request used to rebuild the whole
    graph and leak a DB connection each call. Overridden in tests to inject a
    FakeLLM-backed graph.
    """
    graph = getattr(request.app.state, "travel_graph", None)
    if graph is None:
        raise UpstreamError("Agent graph is not available")
    return graph


GraphDep = Annotated[Any, Depends(get_travel_graph)]
SessionDep = Annotated[Session, Depends(get_session)]


def _thread_id(req: ChatRequest, conversation_id: str) -> str:
    return f"user_{req.user_id}_trip_{req.trip_id or 'none'}_conv_{conversation_id}"


def _config(thread_id: str, req: ChatRequest) -> dict:
    from app.agents.observability import callbacks, trace_metadata

    return {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": get_settings().agent_recursion_limit,
        "callbacks": callbacks(),
        "metadata": trace_metadata(req.user_id, req.trip_id),
    }


@router.post("/chat", response_model=ChatResponse, summary="Send a turn to the agent")
async def agent_chat(
    body: ChatRequest, graph: GraphDep, session: SessionDep
) -> ChatResponse:
    repo = ConversationRepository(session)
    conversation_id = (
        body.conversation_id
        or repo.create_conversation(user_id=body.user_id, trip_id=body.trip_id).id
    )
    cfg = _config(_thread_id(body, conversation_id), body)

    if body.resume is not None:
        # Resume a graph paused at a plan-approval interrupt.
        result = await graph.ainvoke(Command(resume=body.resume), cfg)
    else:
        repo.append_message(
            conversation_id=conversation_id, role="user", content=body.message
        )
        result = await graph.ainvoke(
            {
                "messages": [HumanMessage(content=body.message)],
                "user_id": body.user_id,
                "trip_id": body.trip_id,
            },
            cfg,
        )

    interrupts = result.get("__interrupt__", [])
    interrupt_pending = bool(interrupts)
    interrupt_payload = interrupts[0].value if interrupts else None

    if interrupt_pending:
        reply = ""
    else:
        # Pick the last *assistant* message, not result["messages"][-1] blindly: a
        # ReAct sub-agent that exhausts the recursion limit can leave a ToolMessage
        # (raw JSON) as the final entry, which must never surface as the reply.
        ai_messages = [m for m in result["messages"] if isinstance(m, AIMessage)]
        reply = ai_messages[-1].content if ai_messages else ""
        repo.append_message(
            conversation_id=conversation_id, role="assistant", content=reply
        )

    return ChatResponse(
        conversation_id=conversation_id,
        reply=reply,
        current_flow=result.get("current_flow"),
        interrupt_pending=interrupt_pending,
        interrupt_payload=interrupt_payload,
    )


@router.post("/stream", summary="Stream the agent's reply as Server-Sent Events")
async def agent_stream(body: ChatRequest, graph: GraphDep):
    from uuid import uuid4

    from app.streaming.mapper import stream_agent_events

    # Must use caller-supplied conversation_id for resume so the checkpoint thread
    # matches; fallback to a generated id only for fresh (non-resume) turns.
    conversation_id = body.conversation_id or f"stream-{uuid4().hex[:12]}"
    cfg = _config(_thread_id(body, conversation_id), body)

    if body.resume is not None:
        # Resume a graph paused at a plan-approval interrupt; the same cfg
        # (thread_id) addresses the checkpoint created during the initial turn.
        stream_input = Command(resume=body.resume)
    else:
        stream_input = {
            "messages": [HumanMessage(content=body.message)],
            "user_id": body.user_id,
            "trip_id": body.trip_id,
        }

    return sse_response(
        stream_agent_events(
            graph, stream_input, cfg=cfg, conversation_id=conversation_id
        )
    )


@router.get(
    "/manifest", response_model=AgentManifest, summary="Agent capability manifest"
)
def agent_manifest() -> AgentManifest:
    from app.agents.supervisor import SUBAGENTS

    tools = [
        ToolManifestEntry(
            name=t.name,
            description=(t.description or "").strip().split("\n")[0],
            read_only=TOOL_METADATA[t.name]["readOnly"],
            destructive=TOOL_METADATA[t.name]["destructive"],
        )
        for t in ALL_TOOLS
    ]
    return AgentManifest(subagents=list(SUBAGENTS), tools=tools)
