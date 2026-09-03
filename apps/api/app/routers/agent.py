"""Agent endpoints — /agent/chat, /agent/stream, /agent/manifest.

specs/travel-agent Task 6.1. The compiled graph is resolved through
``get_travel_graph`` so tests swap in a FakeLLM-backed graph with one override.
Conversations/messages are persisted alongside the LangGraph checkpointer (which
owns the live thread state).
"""

from __future__ import annotations

import logging
import time
from dataclasses import replace
from typing import Annotated, Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command
from sqlalchemy.orm import Session, sessionmaker
from starlette.background import BackgroundTask

from app.agents.constants import AGENT_ERROR_FALLBACK_MSG
from app.agents.context import AgentContext, resolve_agent_context
from app.agents.graph import resolve_travel_graph
from app.agents.guardrails import redact_pii
from app.agents.metrics import TurnMetricsHandler
from app.agents.observability import callbacks, trace_metadata
from app.agents.suggestions import profile_for_suggestions, suggestions_for_flow
from app.agents.supervisor import SUBAGENTS
from app.core.agent_config_cache import AgentConfigCache
from app.core.auth import CurrentUserDep
from app.core.config import get_settings
from app.core.pricing import estimate_cost
from app.core.streaming import sse_response
from app.db.base import _utc_now_iso
from app.db.session import get_session
from app.enums import Tier
from app.exceptions import ForbiddenError, UpstreamError
from app.memory.extraction_runner import (
    run_memory_extraction,
    run_memory_extraction_from_stream,
)
from app.repositories.agent_run import AgentRunRepository
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
    TurnUsage,
)
from app.schemas.error import error_responses
from app.services.quota_service import check_quota
from app.streaming.agent_run import record_agent_run
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


def _config(
    thread_id: str,
    user_id: str,
    trip_id: str | None,
    *,
    run_id: str,
    metrics: TurnMetricsHandler,
) -> dict:
    """Build the configuration for the agent.

    :param thread_id: The thread id for the conversation.
    :param user_id: The effective user id (JWT sub or anonymous).
    :param trip_id: The trip id, if any.
    :param run_id: The router-minted run id; set as the LangChain root ``run_id``
        (langfuse derives its trace id from OTel context, not this) so the turn's
        metrics correlate with the ``agent_runs`` row.
    :param metrics: The per-turn ``TurnMetricsHandler``, attached alongside the
        tracing callbacks so it observes the whole run.
    :return: The configuration for the agent.
    """
    return {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": get_settings().agent_recursion_limit,
        "callbacks": callbacks() + [metrics],
        "metadata": trace_metadata(user_id, trip_id),
        "run_id": UUID(run_id),
    }


def _turn_input(message: str, user_id: str, trip_id: str | None) -> dict:
    """Build the graph-invocation input for a new user turn.

    ``trip_id`` is included only when the client supplied one. LangGraph
    merges an invocation's input into the loaded checkpoint state per
    channel; ``TravelAgentState.trip_id`` has no reducer, so a channel key
    absent from the input keeps its checkpointed value, while an explicit
    ``None`` would overwrite it. The web client has no way to learn a
    trip_id the ``create_trip`` tool set mid-conversation, so it keeps
    sending ``trip_id: null`` on every later turn — passing that through
    unconditionally clobbered the checkpoint's trip_id back to ``None`` on
    the very next turn (specs/fix-trip-id-persist-across-turns).

    :param message: The traveller's message for this turn.
    :param user_id: The effective user id (JWT sub or anonymous).
    :param trip_id: The client-declared trip id, or None if the client has
        no active trip context.
    :return: The input dict for ``graph.ainvoke``.
    """
    # Defense-in-depth: redact email/card PII before the message reaches the
    # graph, the checkpointer, or the conversation DB. The graph's pii_guardrail
    # node also redacts, but sanitizing here protects paths that persist the
    # raw turn before the graph runs.
    safe_message = redact_pii(message)
    turn_input: dict = {
        "messages": [HumanMessage(content=safe_message)],
        "user_id": user_id,
    }
    if trip_id is not None:
        turn_input["trip_id"] = trip_id
    return turn_input


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


def _resolve_timezone(raw: str | None) -> str:
    """Return a valid IANA tz string, falling back to the configured default.

    The client sends its detected timezone; a missing or invalid value must not
    fail the request — we ground dates against ``settings.agent_timezone`` instead.

    :param raw: Client-supplied IANA timezone name, or None.
    :return: A valid IANA timezone name.
    """
    default = get_settings().agent_timezone
    if not raw:
        return default
    try:
        ZoneInfo(raw)
        return raw
    except Exception:
        logger.warning(
            "[agent] invalid timezone %r from client; using %s", raw, default
        )
        return default


def _resolve_context(
    effective_user_id: str,
    authenticated: bool,
    session: Session,
) -> AgentContext:
    """Resolve the per-run AgentContext (tier resolved server-side).

    Security: ``tier`` is resolved server-side from the users table and is never
    read from the request body.  When authenticated the effective Supabase id is
    used; anonymous callers are always ``free`` (no DB lookup needed).

    The per-request timezone is applied by the caller via ``replace`` (it comes
    from the request body, unlike the server-resolved tier).

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
    return resolve_agent_context(
        tier=tier, allow_reflection=allow_reflection, authenticated=authenticated
    )


@router.post("/chat", response_model=ChatResponse, summary="Send a turn to the agent")
async def agent_chat(
    body: ChatRequest,
    graph: GraphDep,
    session: SessionDep,
    auth_user: CurrentUserDep,
    background: BackgroundTasks,
) -> ChatResponse:
    """Send a chat request to the agent.

    :param body: The request body.
    :param graph: The compiled LangGraph graph.
    :param session: The request-scoped DB session.
    :param auth_user: The authenticated user (a valid Supabase JWT is required).
    :param background: FastAPI background-task queue; used to run memory
        extraction after the reply is returned, off the request's critical path.
    :return: The chat response.
    """
    uid = auth_user.id
    repo = ConversationRepository(session)
    ctx = _resolve_context(uid, True, session)
    ctx = replace(ctx, timezone=_resolve_timezone(body.timezone))
    # Quota guard — raises QuotaExceededError (429) before any work begins.
    check_quota(user_id=uid, tier=ctx.tier, repo=repo)

    conversation_id = repo.ensure_conversation(
        conversation_id=body.conversation_id,
        user_id=uid,
        trip_id=body.trip_id,
    )
    thread_id = _thread_id(uid, body.trip_id, conversation_id)

    # Per-turn metrics: mint the run id up front so the row correlates with the
    # in-flight turn, attach the handler via cfg, and start the ``agent_runs``
    # row (committed by the existing session.commit() below). All of this is
    # best-effort — no metrics failure may raise into the reply path.
    run_id = str(uuid4())
    metrics = TurnMetricsHandler()
    started = time.monotonic()
    kind = "resume" if body.resume is not None else "turn"
    try:
        AgentRunRepository(session).start(
            run_id,
            user_id=uid,
            conversation_id=conversation_id,
            thread_id=thread_id,
            trip_id=body.trip_id,
            channel="chat",
            kind=kind,
            started_at=_utc_now_iso(),
        )
    except Exception:
        logger.exception("[agent_chat] failed to start agent_run id=%s", run_id)

    cfg = _config(thread_id, uid, body.trip_id, run_id=run_id, metrics=metrics)

    def _finalize(status: str, current_flow: str | None) -> TurnUsage | None:
        """Close metrics, finalize the run row, and return client usage (best-effort)."""
        usage: TurnUsage | None = None
        try:
            metrics.close(started)
            metrics.cost_usd = estimate_cost(metrics.snapshot()["by_model"])
            usage = TurnUsage(**metrics.public())
        except Exception:
            logger.exception("[agent_chat] failed to build usage id=%s", run_id)
        try:
            AgentRunRepository(session).finish(
                run_id,
                status=status,
                current_flow=current_flow,
                finished_at=_utc_now_iso(),
                metrics=metrics.snapshot(),
            )
        except Exception:
            logger.exception("[agent_chat] failed to finish agent_run id=%s", run_id)
        return usage

    try:
        if body.resume is not None:
            # Commit (and release the SQLite write lock) before the graph runs
            # so a tool's own session_scope() (e.g. create_trip) can write.
            # For Postgres this is harmless; for SQLite it prevents "database
            # is locked" — mirrors the /stream handler below.
            session.commit()
            # Resume a graph paused at a plan-approval interrupt.
            result = await graph.ainvoke(Command(resume=body.resume), cfg, context=ctx)
        else:
            # Sanitize PII before it touches the conversation store or the graph.
            safe_message = redact_pii(body.message)
            repo.append_message(
                conversation_id=conversation_id, role="user", content=safe_message
            )
            session.commit()
            result = await graph.ainvoke(
                _turn_input(safe_message, uid, body.trip_id),
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
        # The failed graph run may still have left a checkpointed trip_id from
        # an earlier turn's create_trip (this turn's own state update, if any,
        # never committed). Report that instead of the request's trip_id —
        # which _turn_input intentionally omits/leaves stale — so a client
        # reading this field doesn't see a spurious null. Best-effort.
        fallback_trip_id = body.trip_id
        try:
            checkpoint = await graph.aget_state(cfg)
            if checkpoint and checkpoint.values:
                fallback_trip_id = checkpoint.values.get("trip_id", body.trip_id)
        except Exception:  # noqa: BLE001 — best-effort; fall back to body.trip_id
            pass
        usage = _finalize("failed", None)
        return ChatResponse(
            conversation_id=conversation_id,
            reply=reply,
            trip_id=fallback_trip_id,
            current_flow=None,
            suggestions=[],
            interrupt_pending=False,
            interrupt_payload=None,
            usage=usage,
        )

    interrupts = result.get("__interrupt__", [])
    interrupt_pending = bool(interrupts)
    interrupt_payload = interrupts[0].value if interrupts else None

    if interrupt_pending:
        reply = ""
    else:
        # Scope to messages produced THIS turn, after the last HumanMessage, so
        # prior turns' AIMessages in the full thread history are never included.
        # A multi-intent turn runs two or more sub-agents sequentially, but each
        # sub-agent is a full ReAct loop that regenerates the whole answer for
        # the turn, not a slice. The turn's final user-facing answer is therefore
        # the last content-bearing, non-tool-calling AIMessage in this turn. A
        # reflection REVISE appends a fresh AIMessage after the REVISE note, so
        # the last such message is also the revised answer. A ReAct loop that
        # exhausted the recursion limit may leave a ToolMessage as the final
        # entry; filtering to AIMessage excludes it.
        turn_messages = result["messages"]
        for i in range(len(turn_messages) - 1, -1, -1):
            if isinstance(turn_messages[i], HumanMessage):
                turn_messages = turn_messages[i:]
                break
        reply = next(
            (
                m.content
                for m in reversed(turn_messages)
                if isinstance(m, AIMessage) and m.content and not m.tool_calls
            ),
            AGENT_ERROR_FALLBACK_MSG,
        )
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
            run_id=run_id,
            session_factory=_isolated_factory(session),
        )

    usage = _finalize(
        "interrupted" if interrupt_pending else "completed",
        result.get("current_flow"),
    )

    return ChatResponse(
        conversation_id=conversation_id,
        reply=reply,
        trip_id=result.get("trip_id"),
        current_flow=result.get("current_flow"),
        suggestions=(
            []
            if interrupt_pending
            else suggestions_for_flow(
                result.get("current_flow"),
                trip_facts=result.get("trip_facts"),
                profile=profile_for_suggestions(graph.store, uid),
                preferences=result.get("preferences", ""),
            )
        ),
        interrupt_pending=interrupt_pending,
        interrupt_payload=interrupt_payload,
        usage=usage,
    )


@router.post("/stream", summary="Stream the agent's reply as Server-Sent Events")
async def agent_stream(
    body: ChatRequest,
    graph: GraphDep,
    session: SessionDep,
    auth_user: CurrentUserDep,
):
    """Stream the agent's reply as Server-Sent Events.

    :param body: The request body.
    :param graph: The compiled LangGraph graph.
    :param session: The request-scoped DB session (used to create/look up the
        conversation and append the user message before streaming begins).
    :param auth_user: The authenticated user (a valid Supabase JWT is required).
    :return: A streaming response of Server-Sent Events.
    """
    uid = auth_user.id
    repo = ConversationRepository(session)
    ctx = _resolve_context(uid, True, session)
    ctx = replace(ctx, timezone=_resolve_timezone(body.timezone))
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
    thread_id = _thread_id(uid, body.trip_id, conversation_id)

    # Per-turn metrics: mint the run id, attach the handler via cfg, and start the
    # ``agent_runs`` row before the session.commit() below persists it. The stream
    # recorder (record_agent_run) finalizes it once the SSE stream drains.
    run_id = str(uuid4())
    metrics = TurnMetricsHandler()
    kind = "resume" if body.resume is not None else "turn"
    try:
        AgentRunRepository(session).start(
            run_id,
            user_id=uid,
            conversation_id=conversation_id,
            thread_id=thread_id,
            trip_id=body.trip_id,
            channel="stream",
            kind=kind,
            started_at=_utc_now_iso(),
        )
    except Exception:
        logger.exception("[agent_stream] failed to start agent_run id=%s", run_id)

    cfg = _config(thread_id, uid, body.trip_id, run_id=run_id, metrics=metrics)

    if body.resume is not None:
        # Resume a graph paused at a plan-approval interrupt; the same cfg
        # (thread_id) addresses the checkpoint created during the initial turn.
        stream_input = Command(resume=body.resume)
    else:
        # Sanitize PII before it touches the conversation store or the graph.
        safe_message = redact_pii(body.message)
        # Persist the user turn before returning the StreamingResponse so the
        # message row exists even if the stream is abandoned mid-flight. On a
        # retry the user message is already saved (the previous turn was
        # interrupted before the assistant reply persisted), so skip re-appending
        # it to avoid a duplicate question bubble.
        if not body.retry:
            repo.append_message(
                conversation_id=conversation_id, role="user", content=safe_message
            )
        stream_input = _turn_input(safe_message, uid, body.trip_id)

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
        run_id=run_id,
        session_factory=factory,
    )

    return sse_response(
        persist_assistant_turn(
            record_agent_run(
                stream_agent_events(
                    graph,
                    stream_input,
                    cfg=cfg,
                    conversation_id=conversation_id,
                    context=ctx,
                    final_state_sink=sink,
                    metrics=metrics,
                ),
                run_id=run_id,
                metrics=metrics,
                session_factory=factory,
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
    auth_user: CurrentUserDep,
    user_id: str | None = None,
) -> list[Conversation]:
    """Return all conversations for the authenticated user, newest first.

    Identity is the JWT sub; the ``user_id`` query param is deprecated and
    ignored (no enumeration of another user's conversations). Returns an empty
    list for a user with no conversations (matches the repo contract).

    :param session: The request-scoped DB session.
    :param auth_user: The authenticated user (a valid Supabase JWT is required).
    :param user_id: Deprecated and ignored; identity comes from the JWT.
    :return: The user's conversations, newest first.
    """
    uid = auth_user.id
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
    auth_user: CurrentUserDep,
    user_id: str | None = None,
) -> list[Message]:
    """Return all messages for the given conversation, oldest first.

    Ownership-scoped: the caller must be the conversation's owner. Identity is
    the JWT sub; the ``user_id`` query param is deprecated and ignored (no
    spoofing). Returns an empty list for an unknown conversation or one owned by
    someone else — this neither leaks message contents nor confirms a
    conversation's existence.

    :param conversation_id: The conversation to list messages for.
    :param session: The request-scoped DB session.
    :param auth_user: The authenticated user (a valid Supabase JWT is required).
    :param user_id: Deprecated and ignored; identity comes from the JWT.
    :return: The conversation's messages, oldest first.
    """
    uid = auth_user.id
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
