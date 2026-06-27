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
from sqlalchemy.orm import Session, sessionmaker

from app.agents.observability import callbacks, trace_metadata
from app.agents.supervisor import SUBAGENTS
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
    Conversation,
    Message,
    ToolManifestEntry,
)
from app.schemas.error import error_responses
from app.streaming.mapper import stream_agent_events
from app.streaming.persistence import persist_assistant_turn
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
    """
    Build the thread id for the conversation.

    The thread id is a unique identifier for the conversation. It is used to
    identify the conversation in the database and to identify the conversation in
    the LangGraph checkpointer.
    """
    return f"user_{req.user_id}_trip_{req.trip_id or 'none'}_conv_{conversation_id}"


def _config(thread_id: str, req: ChatRequest) -> dict:
    """
    Build the configuration for the agent.

    :param thread_id: The thread id for the conversation.
    :param req: The request object.
    :return: The configuration for the agent.
    """

    return {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": get_settings().agent_recursion_limit,
        "callbacks": callbacks(),
        "metadata": trace_metadata(req.user_id, req.trip_id),
    }


def _isolated_factory(session: Session) -> sessionmaker[Session]:
    """Sessionmaker bound to ``session``'s engine, for use after the request ends.

    The agent SSE generator outlives the request-scoped session, so it persists
    the assistant turn through its own session. Binding to the request session's
    *engine* (rather than a stringified URL — ``str(URL)`` masks the password as
    ``***`` and breaks Postgres auth) reuses the same pool/credentials, and keeps
    test ``get_session`` overrides flowing through to the generator.
    """
    return sessionmaker(bind=session.get_bind(), expire_on_commit=False, future=True)


@router.post("/chat", response_model=ChatResponse, summary="Send a turn to the agent")
async def agent_chat(
    body: ChatRequest, graph: GraphDep, session: SessionDep
) -> ChatResponse:
    """
    Send a chat request to the agent.

    :param body: The request body.
    :param graph: The graph.
    :param session: The session.
    :return: The response.
    """
    repo = ConversationRepository(session)
    conversation_id = repo.ensure_conversation(
        conversation_id=body.conversation_id,
        user_id=body.user_id,
        trip_id=body.trip_id,
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
async def agent_stream(body: ChatRequest, graph: GraphDep, session: SessionDep):
    """
    Stream the agent's reply as Server-Sent Events.

    :param body: The request body.
    :param graph: The graph.
    :param session: The request-scoped DB session (used to create/look up the
        conversation and append the user message before streaming begins).
    :return: The response.
    """
    repo = ConversationRepository(session)
    # Resolve or create the conversation row before streaming so the row always
    # exists (no orphaned messages) and thread_id is stable. get-or-create also
    # handles client-minted ids and ids restored across reloads.
    conversation_id = repo.ensure_conversation(
        conversation_id=body.conversation_id,
        user_id=body.user_id,
        trip_id=body.trip_id,
    )
    cfg = _config(_thread_id(body, conversation_id), body)

    if body.resume is not None:
        # Resume a graph paused at a plan-approval interrupt; the same cfg
        # (thread_id) addresses the checkpoint created during the initial turn.
        stream_input = Command(resume=body.resume)
    else:
        # Persist the user turn before returning the StreamingResponse so the
        # message row exists even if the stream is abandoned mid-flight.
        repo.append_message(
            conversation_id=conversation_id, role="user", content=body.message
        )
        stream_input = {
            "messages": [HumanMessage(content=body.message)],
            "user_id": body.user_id,
            "trip_id": body.trip_id,
        }

    # Commit (and release the SQLite write lock) before streaming begins so
    # the isolated factory session inside persist_assistant_turn can write.
    # For Postgres this is harmless; for SQLite it prevents "database is locked".
    # The dependency's cleanup commit is a no-op after an explicit commit here.
    session.commit()

    # Bind an isolated sessionmaker to the request session's *engine* (not a
    # stringified URL — str(URL) masks the password as "***", which breaks
    # Postgres auth in the stream generator). Reuses the same engine/pool the
    # request used, so test overrides via get_session still propagate.
    factory = _isolated_factory(session)

    return sse_response(
        persist_assistant_turn(
            stream_agent_events(
                graph, stream_input, cfg=cfg, conversation_id=conversation_id
            ),
            conversation_id=conversation_id,
            session_factory=factory,
        )
    )


@router.get(
    "/conversations",
    response_model=list[Conversation],
    summary="List conversations for a user",
)
def list_conversations(user_id: str, session: SessionDep) -> list[Conversation]:
    """Return all conversations for the given user, newest first.

    Returns an empty list for an unknown user_id (matches the repo contract).
    """
    repo = ConversationRepository(session)
    return repo.list_for_user(user_id)


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=list[Message],
    summary="List messages for a conversation",
)
def list_conversation_messages(
    conversation_id: str, session: SessionDep
) -> list[Message]:
    """Return all messages for the given conversation, oldest first.

    Returns an empty list for an unknown conversation_id (matches the repo contract).
    """
    repo = ConversationRepository(session)
    return repo.list_messages(conversation_id)


@router.get(
    "/manifest", response_model=AgentManifest, summary="Agent capability manifest"
)
def agent_manifest() -> AgentManifest:
    """
    Get the agent capability manifest.
    """
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
