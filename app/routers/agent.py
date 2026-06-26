"""Agent endpoints — /agent/chat, /agent/stream, /agent/manifest.

specs/travel-agent Task 6.1. The compiled graph is resolved through
``get_travel_graph`` so tests swap in a FakeLLM-backed graph with one override.
Conversations/messages are persisted alongside the LangGraph checkpointer (which
owns the live thread state).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from langchain_core.messages import HumanMessage
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
    repo.append_message(
        conversation_id=conversation_id, role="user", content=body.message
    )

    result = await graph.ainvoke(
        {
            "messages": [HumanMessage(content=body.message)],
            "user_id": body.user_id,
            "trip_id": body.trip_id,
        },
        _config(_thread_id(body, conversation_id), body),
    )
    reply = result["messages"][-1].content if result["messages"] else ""
    repo.append_message(
        conversation_id=conversation_id, role="assistant", content=reply
    )
    return ChatResponse(
        conversation_id=conversation_id,
        reply=reply,
        current_flow=result.get("current_flow"),
    )


@router.post("/stream", summary="Stream the agent's reply as Server-Sent Events")
async def agent_stream(body: ChatRequest, graph: GraphDep):
    conversation_id = body.conversation_id or "stream"

    async def tokens():
        async for chunk, _meta in graph.astream(
            {
                "messages": [HumanMessage(content=body.message)],
                "user_id": body.user_id,
                "trip_id": body.trip_id,
            },
            _config(_thread_id(body, conversation_id), body),
            stream_mode="messages",
        ):
            content = getattr(chunk, "content", "")
            if content:
                yield content

    return sse_response(tokens())


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
