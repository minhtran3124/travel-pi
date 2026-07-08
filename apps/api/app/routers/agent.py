"""Agent endpoints — /agent/chat, /agent/stream, /agent/manifest.

specs/travel-agent Task 6.1. The compiled graph is resolved through
``get_travel_graph`` so tests swap in a FakeLLM-backed graph with one override.
Conversations/messages are persisted alongside the LangGraph checkpointer (which
owns the live thread state).
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command
from sqlalchemy.orm import Session, sessionmaker
from starlette.background import BackgroundTask

from app.agents.constants import AGENT_ERROR_FALLBACK_MSG
from app.agents.context import AgentContext, resolve_agent_context
from app.agents.graph import resolve_travel_graph
from app.agents.observability import callbacks, trace_metadata
from app.agents.suggestions import suggestions_for_flow
from app.agents.supervisor import SUBAGENTS
from app.core.agent_config_cache import AgentConfigCache
from app.core.auth import AuthUser, CurrentUserDep, get_current_user_optional
from app.core.config import get_settings
from app.core.streaming import sse_response
from app.db.session import get_session
from app.enums import Tier
from app.exceptions import DomainValidationError, ForbiddenError, UpstreamError
from app.memory.extraction_runner import (
    run_memory_extraction,
    run_memory_extraction_from_stream,
)
from app.repositories.conversation import ConversationRepository
from app.repositories.user import UserRepository
from app.routers.tags import Tags
from app.schemas.agent import (
    AgentManifest,
    ChatRequest,
    ChatResponse,
    ClaimRequest,
    ClaimResult,
    Conversation,
    Message,
    ToolManifestEntry,
)
from app.schemas.error import error_responses
from app.services.quota_service import check_quota
from app.streaming.mapper import stream_agent_events
from app.streaming.persistence import persist_assistant_turn
from app.tools.registry import ALL_TOOLS, TOOL_METADATA

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=[Tags.agent], responses=error_responses(422))


def get_travel_graph(request: Request) -> Any:
    """Return the shared compiled graph built once in ``lifespan`` (REVIEW.md C1).

    The graph + checkpointer + store are constructed a single time at startup and
    held on ``app.state``; resolving them here per request used to rebuild the whole
    graph and leak a DB connection each call. ``resolve_travel_graph`` rebuilds it
    in place only when the DB config generation changed (MIN-47), reusing the same
    checkpointer/store. Overridden in tests to inject a FakeLLM-backed graph.

    :param request: The incoming request, used to reach ``app.state``.
    :return: The shared compiled LangGraph graph.
    """
    graph = resolve_travel_graph(request.app)
    if graph is None:
        raise UpstreamError("Agent graph is not available")

    return graph


GraphDep = Annotated[Any, Depends(get_travel_graph)]
SessionDep = Annotated[Session, Depends(get_session)]
OptionalUserDep = Annotated[AuthUser | None, Depends(get_current_user_optional)]


def _effective_user_id(auth_user: AuthUser | None, fallback: str | None) -> str | None:
    """Return the JWT subject when authenticated, else the anonymous fallback.

    When a valid token is present the client-supplied id (``body.user_id`` /
    query ``user_id``) is intentionally ignored to prevent user-id spoofing.
    Returns ``None`` only when anonymous *and* no fallback id was supplied.

    :param auth_user: The authenticated user, or None for anonymous callers.
    :param fallback: The client-supplied id to use when unauthenticated.
    :return: The effective user id, or None if anonymous with no fallback.
    """
    return auth_user.id if auth_user else fallback


def _thread_id(user_id: str, trip_id: str | None, conversation_id: str) -> str:
    """Build the thread id for the conversation.

    The thread id is a unique identifier for the conversation. It is used to
    identify the conversation in the database and to identify the conversation in
    the LangGraph checkpointer.

    :param user_id: The effective user id (JWT sub or anonymous).
    :param trip_id: The trip id, if any.
    :param conversation_id: The conversation id.
    :return: The composed thread id.
    """
    return f"user_{user_id}_trip_{trip_id or 'none'}_conv_{conversation_id}"


def _config(thread_id: str, user_id: str, trip_id: str | None) -> dict:
    """Build the configuration for the agent.

    :param thread_id: The thread id for the conversation.
    :param user_id: The effective user id (JWT sub or anonymous).
    :param trip_id: The trip id, if any.
    :return: The configuration for the agent.
    """
    return {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": get_settings().agent_recursion_limit,
        "callbacks": callbacks(),
        "metadata": trace_metadata(user_id, trip_id),
    }


def _isolated_factory(session: Session) -> sessionmaker[Session]:
    """Sessionmaker bound to ``session``'s engine, for use after the request ends.

    The agent SSE generator outlives the request-scoped session, so it persists
    the assistant turn through its own session. Binding to the request session's
    *engine* (rather than a stringified URL — ``str(URL)`` masks the password as
    ``***`` and breaks Postgres auth) reuses the same pool/credentials, and keeps
    test ``get_session`` overrides flowing through to the generator.

    :param session: The request-scoped session whose engine to bind to.
    :return: A sessionmaker bound to the same engine/pool as ``session``.
    """
    return sessionmaker(bind=session.get_bind(), expire_on_commit=False, future=True)


def _resolve_context(
    effective_user_id: str,
    authenticated: bool,
    session: Session,
) -> AgentContext:
    """Resolve the per-run AgentContext (tier resolved server-side).

    Security: ``tier`` is resolved server-side from the users table and is never
    read from the request body.  When authenticated the effective Supabase id is
    used; anonymous callers are always ``free`` (no DB lookup needed).

    :param effective_user_id: The effective user id (JWT sub or anonymous).
    :param authenticated: Whether the caller presented a valid JWT.
    :param session: The request-scoped DB session, used for the tier lookup.
    :return: The resolved AgentContext.
    """
    if authenticated:
        user_repo = UserRepository(session)
        user_repo.ensure_user(effective_user_id)
        tier = user_repo.get_tier(effective_user_id)
    else:
        tier = Tier.FREE.value
    refl = AgentConfigCache.get("reflection")
    allow_reflection = True if (refl is None or refl.enabled is None) else refl.enabled
    return resolve_agent_context(tier=tier, allow_reflection=allow_reflection)


@router.post("/chat", response_model=ChatResponse, summary="Send a turn to the agent")
async def agent_chat(
    body: ChatRequest,
    graph: GraphDep,
    session: SessionDep,
    auth_user: OptionalUserDep,
    background: BackgroundTasks,
) -> ChatResponse:
    """Send a chat request to the agent.

    :param body: The request body.
    :param graph: The compiled LangGraph graph.
    :param session: The request-scoped DB session.
    :param auth_user: The authenticated user, or None for anonymous callers.
    :param background: FastAPI background-task queue; used to run memory
        extraction after the reply is returned, off the request's critical path.
    :return: The chat response.
    """
    uid = _effective_user_id(auth_user, body.user_id)
    repo = ConversationRepository(session)
    ctx = _resolve_context(uid, auth_user is not None, session)
    # Quota guard — raises QuotaExceededError (429) before any work begins.
    check_quota(user_id=uid, tier=ctx.tier, repo=repo)

    conversation_id = repo.ensure_conversation(
        conversation_id=body.conversation_id,
        user_id=uid,
        trip_id=body.trip_id,
    )
    cfg = _config(_thread_id(uid, body.trip_id, conversation_id), uid, body.trip_id)

    try:
        if body.resume is not None:
            # Resume a graph paused at a plan-approval interrupt.
            result = await graph.ainvoke(Command(resume=body.resume), cfg, context=ctx)
        else:
            repo.append_message(
                conversation_id=conversation_id, role="user", content=body.message
            )
            result = await graph.ainvoke(
                {
                    "messages": [HumanMessage(content=body.message)],
                    "user_id": uid,
                    "trip_id": body.trip_id,
                },
                cfg,
                context=ctx,
            )
    except Exception:
        # The graph run itself failed (LLM outage, recursion-limit exhaustion on
        # a tool-retry loop, …). Always return a readable message to the user
        # instead of 500ing, and persist it so the conversation history stays
        # consistent. See AGENT_ERROR_FALLBACK_MSG (app/agents/constants.py).
        logger.exception("[agent_chat] graph run failed for conv=%s", conversation_id)
        reply = AGENT_ERROR_FALLBACK_MSG
        repo.append_message(
            conversation_id=conversation_id, role="assistant", content=reply
        )
        return ChatResponse(
            conversation_id=conversation_id,
            reply=reply,
            current_flow=None,
            suggestions=[],
            interrupt_pending=False,
            interrupt_payload=None,
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
        # Guarantee a user-facing reply even when the graph finished without an
        # assistant message (e.g. a ReAct loop that exhausted the recursion limit
        # on repeated tool errors). The user must always get a readable message.
        if not reply:
            reply = AGENT_ERROR_FALLBACK_MSG
        repo.append_message(
            conversation_id=conversation_id, role="assistant", content=reply
        )
        # Schedule memory extraction to run after the response is sent. The
        # interrupt-skip is guaranteed solely by this `else` branch: the runner
        # does NOT check interrupt state — it only re-checks allow_memory_write,
        # user_id, and store. Do not move this call out from under the guard.
        background.add_task(
            run_memory_extraction,
            messages=result["messages"],
            user_id=result.get("user_id"),
            trip_id=result.get("trip_id"),
            plan_approved=result.get("plan_approved", False),
            allow_memory_write=ctx.allow_memory_write,
            store=graph.store,
            llm=graph.extract_memory_llm,
        )

    return ChatResponse(
        conversation_id=conversation_id,
        reply=reply,
        current_flow=result.get("current_flow"),
        suggestions=(
            []
            if interrupt_pending
            else suggestions_for_flow(result.get("current_flow"))
        ),
        interrupt_pending=interrupt_pending,
        interrupt_payload=interrupt_payload,
    )


@router.post("/stream", summary="Stream the agent's reply as Server-Sent Events")
async def agent_stream(
    body: ChatRequest,
    graph: GraphDep,
    session: SessionDep,
    auth_user: OptionalUserDep,
):
    """Stream the agent's reply as Server-Sent Events.

    :param body: The request body.
    :param graph: The compiled LangGraph graph.
    :param session: The request-scoped DB session (used to create/look up the
        conversation and append the user message before streaming begins).
    :param auth_user: The authenticated user, or None for anonymous callers.
    :return: A streaming response of Server-Sent Events.
    """
    uid = _effective_user_id(auth_user, body.user_id)
    repo = ConversationRepository(session)
    ctx = _resolve_context(uid, auth_user is not None, session)
    # Quota guard — raises QuotaExceededError (429) before streaming begins.
    check_quota(user_id=uid, tier=ctx.tier, repo=repo)

    # Resolve or create the conversation row before streaming so the row always
    # exists (no orphaned messages) and thread_id is stable. get-or-create also
    # handles client-minted ids and ids restored across reloads.
    conversation_id = repo.ensure_conversation(
        conversation_id=body.conversation_id,
        user_id=uid,
        trip_id=body.trip_id,
    )
    cfg = _config(_thread_id(uid, body.trip_id, conversation_id), uid, body.trip_id)

    if body.resume is not None:
        # Resume a graph paused at a plan-approval interrupt; the same cfg
        # (thread_id) addresses the checkpoint created during the initial turn.
        stream_input = Command(resume=body.resume)
    else:
        # Persist the user turn before returning the StreamingResponse so the
        # message row exists even if the stream is abandoned mid-flight. On a
        # retry the user message is already saved (the previous turn was
        # interrupted before the assistant reply persisted), so skip re-appending
        # it to avoid a duplicate question bubble.
        if not body.retry:
            repo.append_message(
                conversation_id=conversation_id, role="user", content=body.message
            )
        stream_input = {
            "messages": [HumanMessage(content=body.message)],
            "user_id": uid,
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

    # Populated by stream_agent_events after the SSE stream fully drains; read
    # by the response's background task (below) so memory extraction runs off
    # the reply path, using the final graph state.
    sink: dict = {}
    background_task = BackgroundTask(
        run_memory_extraction_from_stream,
        sink=sink,
        allow_memory_write=ctx.allow_memory_write,
        store=graph.store,
        llm=graph.extract_memory_llm,
    )

    return sse_response(
        persist_assistant_turn(
            stream_agent_events(
                graph,
                stream_input,
                cfg=cfg,
                conversation_id=conversation_id,
                context=ctx,
                final_state_sink=sink,
            ),
            conversation_id=conversation_id,
            session_factory=factory,
        ),
        background=background_task,
    )


@router.get(
    "/conversations",
    response_model=list[Conversation],
    summary="List conversations for a user",
)
def list_conversations(
    session: SessionDep,
    auth_user: OptionalUserDep,
    user_id: str | None = None,
) -> list[Conversation]:
    """Return all conversations for the given user, newest first.

    When authenticated the JWT sub is used and the ``user_id`` query param is
    ignored (no enumeration of another user's conversations) and not required.
    Anonymous callers must supply ``user_id``. Returns an empty list for an
    unknown user (matches the repo contract).

    :param session: The request-scoped DB session.
    :param auth_user: The authenticated user, or None for anonymous callers.
    :param user_id: The user id to list conversations for (anonymous callers only).
    :return: The user's conversations, newest first.
    """
    uid = _effective_user_id(auth_user, user_id)
    if uid is None:
        raise DomainValidationError("user_id is required when not authenticated.")
    repo = ConversationRepository(session)
    return repo.list_for_user(uid)


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=list[Message],
    summary="List messages for a conversation",
)
def list_conversation_messages(
    conversation_id: str,
    session: SessionDep,
    auth_user: OptionalUserDep,
    user_id: str | None = None,
) -> list[Message]:
    """Return all messages for the given conversation, oldest first.

    Ownership-scoped: the caller must be the conversation's owner. When
    authenticated the JWT sub is used and the ``user_id`` query param is ignored
    (no spoofing); anonymous callers must supply their ``user_id``. Returns an
    empty list for an unknown conversation or one owned by someone else — this
    neither leaks message contents nor confirms a conversation's existence.

    :param conversation_id: The conversation to list messages for.
    :param session: The request-scoped DB session.
    :param auth_user: The authenticated user, or None for anonymous callers.
    :param user_id: The user id claiming ownership (anonymous callers only).
    :return: The conversation's messages, oldest first.
    """
    uid = _effective_user_id(auth_user, user_id)
    if uid is None:
        raise DomainValidationError("user_id is required when not authenticated.")
    repo = ConversationRepository(session)
    conversation = repo.get(conversation_id)
    if conversation is None or conversation.user_id != uid:
        return []
    return repo.list_messages(conversation_id)


@router.get(
    "/manifest", response_model=AgentManifest, summary="Agent capability manifest"
)
def agent_manifest() -> AgentManifest:
    """Get the agent capability manifest.

    :return: The available subagents and tools.
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


@router.post(
    "/conversations/claim",
    response_model=ClaimResult,
    summary="Claim anonymous conversation history on login",
    responses=error_responses(401, 403),
)
def claim_conversations(
    body: ClaimRequest,
    session: SessionDep,
    auth_user: CurrentUserDep,
) -> ClaimResult:
    """Reassign conversations from an anonymous id to the authenticated user's id.

    Guards:
    - Returns ``claimed=0`` (no-op) when ``anonymous_user_id`` equals the JWT sub.
    - Returns 403 when ``anonymous_user_id`` has a ``users`` row — it is a
      registered account, not an anonymous id; refusing prevents history theft.

    :param body: The request body carrying the anonymous user id to claim.
    :param session: The request-scoped DB session.
    :param auth_user: The authenticated caller whose id becomes the new owner.
    :return: The number of conversations claimed.
    """
    sub = auth_user.id
    anon = body.anonymous_user_id

    if anon == sub:
        return ClaimResult(claimed=0)

    user_repo = UserRepository(session)
    if user_repo.exists(anon):
        raise ForbiddenError(
            "The source id belongs to a registered account and cannot be claimed."
        )

    count = ConversationRepository(session).reassign_user(
        from_user_id=anon, to_user_id=sub
    )
    return ClaimResult(claimed=count)
