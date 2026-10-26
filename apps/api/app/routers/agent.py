"""Agent endpoints — /agent/chat, /agent/stream, /agent/manifest.

Conversations/messages are persisted alongside the LangGraph checkpointer, which owns the live thread state.
"""

from __future__ import annotations

import asyncio
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

from app.agents.context import AgentContext, resolve_agent_context
from app.agents.copy import system_reply
from app.agents.graph import resolve_travel_graph
from app.agents.guardrails import redact_pii
from app.agents.metrics import TurnMetricsHandler
from app.agents.observability import callbacks, trace_metadata
from app.agents.prompt_map import enrich_steps
from app.agents.suggestions import profile_for_suggestions, suggestions_for_flow
from app.agents.supervisor import SUBAGENTS
from app.clients.llm_errors import classify_provider_error
from app.core.agent_config_cache import AgentConfigCache
from app.core.auth import CurrentUserDep
from app.core.config import get_settings
from app.core.pricing import estimate_cost
from app.core.streaming import sse_response
from app.db.base import _utc_now_iso
from app.db.session import get_session
from app.enums import MessageRole, Tier
from app.exceptions import ConflictError, ForbiddenError, NotFoundError, UpstreamError
from app.memory.extraction_runner import (
    run_memory_extraction,
    run_memory_extraction_from_stream,
)
from app.repositories.agent_run import AgentRunRepository
from app.repositories.conversation import ConversationRepository
from app.repositories.feedback import FeedbackRepository
from app.repositories.user import UserRepository
from app.routers.tags import Tags
from app.schemas.agent import (
    AgentManifest,
    ChatRequest,
    ChatResponse,
    ClaimRequest,
    ClaimResult,
    Conversation,
    ConversationMessages,
    ToolManifestEntry,
    TurnUsage,
)
from app.schemas.error import error_responses
from app.services.feedback_service import is_rateable
from app.services.quota_service import check_quota
from app.streaming.agent_run import record_agent_run
from app.streaming.mapper import stream_agent_events
from app.streaming.persistence import persist_assistant_turn
from app.tools.registry import ALL_TOOLS, TOOL_METADATA

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=[Tags.agent], responses=error_responses(422))


def get_travel_graph(request: Request) -> Any:
    """Return the shared compiled graph built once at startup; ``resolve_travel_graph`` rebuilds it in place only when the DB config generation changed."""
    graph = resolve_travel_graph(request.app)
    if graph is None:
        raise UpstreamError("Agent graph is not available")

    return graph


GraphDep = Annotated[Any, Depends(get_travel_graph)]


def get_travel_graph_optional(request: Request) -> Any | None:
    """Like ``get_travel_graph`` but returns ``None`` instead of raising, so a read-only route can degrade gracefully (a raising Depends would fail the route before its body runs)."""
    return resolve_travel_graph(request.app)


GraphOptionalDep = Annotated[Any | None, Depends(get_travel_graph_optional)]
SessionDep = Annotated[Session, Depends(get_session)]


def _thread_id(user_id: str, trip_id: str | None, conversation_id: str) -> str:
    """Build the LangGraph checkpointer thread id for the conversation."""
    return f"user_{user_id}_trip_{trip_id or 'none'}_conv_{conversation_id}"


def _config(
    thread_id: str,
    user_id: str,
    trip_id: str | None,
    *,
    run_id: str,
    metrics: TurnMetricsHandler,
) -> dict:
    """Build the graph-invocation config; ``run_id`` is the LangChain root run_id so the turn's metrics correlate with the ``agent_runs`` row."""
    settings = get_settings()
    cfg: dict = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": settings.agent_recursion_limit,
        "callbacks": callbacks() + [metrics],
        "metadata": trace_metadata(user_id, trip_id),
        "run_id": UUID(run_id),
    }
    if settings.agent_max_concurrency is not None:
        cfg["max_concurrency"] = settings.agent_max_concurrency
    return cfg


def _turn_input(
    message: str, user_id: str, trip_id: str | None, account_email: str | None
) -> dict:
    """Build the graph-invocation input for a new user turn.

    ``trip_id`` is included only when the client supplied one: the state channel has no reducer, so omitting the key keeps the checkpointed value while an explicit ``None`` would clobber a trip_id set mid-conversation.
    """
    # Defense-in-depth: mask credit-card PII before it reaches the graph, checkpointer, or DB (some paths persist the raw turn before the graph runs).
    safe_message = redact_pii(message)
    turn_input: dict = {
        "messages": [HumanMessage(content=safe_message)],
        "user_id": user_id,
        "account_email": account_email,
    }
    if trip_id is not None:
        turn_input["trip_id"] = trip_id
    return turn_input


def _isolated_factory(session: Session) -> sessionmaker[Session]:
    """Sessionmaker bound to ``session``'s engine, for the SSE generator that outlives the request; bind to the engine (not ``str(URL)``, which masks the password and breaks Postgres auth)."""
    return sessionmaker(bind=session.get_bind(), expire_on_commit=False, future=True)


def _resolve_timezone(raw: str | None) -> str:
    """Return a valid IANA tz string, falling back to the configured default; a missing or invalid client value must not fail the request."""
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
    """Resolve the per-run AgentContext; ``tier`` is resolved server-side from the users table, never read from the request body (anonymous callers are always ``free``)."""
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


def _open_conversation(
    repo: ConversationRepository, body: ChatRequest, user_id: str
) -> str:
    """Get-or-create the conversation for this turn; a conversation owned by someone else reads as missing (no existence leak), and a resume needs an existing one."""
    if body.conversation_id is not None:
        existing = repo.get(body.conversation_id)
        if existing is not None and existing.user_id != user_id:
            raise NotFoundError("Conversation not found.")
        if existing is None and body.resume is not None:
            raise NotFoundError("Conversation not found.")
    return repo.ensure_conversation(
        conversation_id=body.conversation_id, user_id=user_id, trip_id=body.trip_id
    )


async def _require_pending_interrupt(graph: Any, cfg: dict) -> None:
    """A resume only makes sense against a paused thread; otherwise it would be forwarded to the LLM as a bogus turn."""
    state = await graph.aget_state(cfg)
    if not (state and state.interrupts):
        raise ConflictError("No pending interrupt to resume for this conversation.")


@router.post("/chat", response_model=ChatResponse, summary="Send a turn to the agent")
async def agent_chat(
    body: ChatRequest,
    graph: GraphDep,
    session: SessionDep,
    auth_user: CurrentUserDep,
    background: BackgroundTasks,
) -> ChatResponse:
    """Send a chat request to the agent."""
    uid = auth_user.id
    repo = ConversationRepository(session)
    ctx = _resolve_context(uid, True, session)
    ctx = replace(ctx, timezone=_resolve_timezone(body.timezone))
    # Quota guard — raises QuotaExceededError (429) before any work begins.
    check_quota(user_id=uid, tier=ctx.tier, repo=repo)

    conversation_id = _open_conversation(repo, body, uid)
    thread_id = _thread_id(uid, body.trip_id, conversation_id)
    if body.resume is not None:
        await _require_pending_interrupt(
            graph, {"configurable": {"thread_id": thread_id}}
        )

    # Metrics are best-effort — no failure here may raise into the reply path.
    run_id = str(uuid4())
    # Minted up front so the response, history and feedback all name the same message.
    assistant_message_id = str(uuid4())
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
            # Sweep steps whose close hook never fired (a graph failure can leave a cancelled branch open), so chat and stream record a failure identically.
            metrics.close_if_open()
            metrics.cost_usd = estimate_cost(metrics.snapshot()["by_model"])
            usage = TurnUsage(**metrics.public())
        except Exception:
            logger.exception("[agent_chat] failed to build usage id=%s", run_id)
        # The prompt snapshot the running graph baked in at build time, not whatever `active.yaml` says now.
        prompt_versions = getattr(graph, "prompt_versions", None)
        try:
            AgentRunRepository(session).finish(
                run_id,
                status=status,
                current_flow=current_flow,
                finished_at=_utc_now_iso(),
                metrics=metrics.snapshot(),
                prompt_versions=prompt_versions,
            )
        except Exception:
            logger.exception("[agent_chat] failed to finish agent_run id=%s", run_id)
        try:
            # Steps written on the request session before its commit — a background task against the flushed-but-uncommitted row deadlocks.
            AgentRunRepository(session).add_steps(
                run_id, enrich_steps(metrics.steps(), prompt_versions)
            )
        except Exception:
            logger.exception("[agent_chat] failed to add steps id=%s", run_id)
        try:
            # Commit the post-graph writes explicitly: writes made on the request session after the graph `await` otherwise never reach the DB, leaving the row `running` forever.
            session.commit()
        except Exception:
            logger.exception("[agent_chat] failed to commit turn id=%s", run_id)
            # Roll back so the session is usable again; otherwise the dependency's teardown commit raises and surfaces a 500 on a good reply.
            try:
                session.rollback()
            except Exception:
                logger.exception("[agent_chat] rollback failed id=%s", run_id)
        return usage

    try:
        if body.resume is not None:
            # Commit before the graph runs so a tool's own session_scope() can write (SQLite: prevents "database is locked").
            session.commit()
            result = await graph.ainvoke(Command(resume=body.resume), cfg, context=ctx)
        else:
            safe_message = redact_pii(body.message)
            repo.append_message(
                conversation_id=conversation_id, role="user", content=safe_message
            )
            session.commit()
            result = await graph.ainvoke(
                _turn_input(safe_message, uid, body.trip_id, auth_user.email),
                cfg,
                context=ctx,
            )
    except Exception as exc:
        # Graph run failed: return a readable message instead of 500ing, and persist it so history stays consistent.
        logger.exception("[agent_chat] graph run failed for conv=%s", conversation_id)
        failure = classify_provider_error(exc)
        if failure is not None:
            # Auth/availability failures are not a "reply": surface them as 502 (sanitized) instead of a 200 that hides the misconfiguration.
            _finalize("failed", None)
            raise UpstreamError(failure.message) from None
        # Language from the pre-turn checkpoint (best-effort; default English).
        try:
            _pre = await graph.aget_state(cfg)
            _lang = (_pre.values or {}).get("language") if _pre else None
        except Exception:  # noqa: BLE001 — fallback must never fail
            _lang = None
        # Off the loop: a first miss per language runs a blocking translation.
        reply = await asyncio.to_thread(system_reply, "agent_error_fallback", _lang)
        # The run finishes `failed`, so the feedback service refuses to rate it.
        repo.append_message(
            conversation_id=conversation_id,
            role="assistant",
            content=reply,
            message_id=assistant_message_id,
            agent_run_id=run_id,
        )
        # Report the checkpointed trip_id from an earlier turn rather than the request's (possibly stale) one, so a client doesn't see a spurious null. Best-effort.
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
            assistant_message_id=assistant_message_id,
            agent_run_id=run_id,
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
        # The turn's answer is the last content-bearing, non-tool-calling AIMessage after this turn's HumanMessage, so prior turns and a trailing ToolMessage are excluded.
        turn_messages = result["messages"]
        for i in range(len(turn_messages) - 1, -1, -1):
            if isinstance(turn_messages[i], HumanMessage):
                turn_messages = turn_messages[i:]
                break
        reply = next(
            (
                m.text
                for m in reversed(turn_messages)
                if isinstance(m, AIMessage) and m.text and not m.tool_calls
            ),
            None,
        ) or await asyncio.to_thread(
            system_reply, "agent_error_fallback", result.get("language")
        )
        repo.append_message(
            conversation_id=conversation_id,
            role="assistant",
            content=reply,
            message_id=assistant_message_id,
            agent_run_id=run_id,
        )
        # The interrupt-skip is guaranteed solely by this `else` branch: the runner does NOT check interrupt state. Do not move this call out from under the guard.
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
        # No reply row is written on an interrupt, so there is nothing to rate.
        assistant_message_id=None if interrupt_pending else assistant_message_id,
        agent_run_id=run_id,
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
                allowed_subagents=ctx.allowed_subagents,
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
    """Stream the agent's reply as Server-Sent Events."""
    uid = auth_user.id
    repo = ConversationRepository(session)
    ctx = _resolve_context(uid, True, session)
    ctx = replace(ctx, timezone=_resolve_timezone(body.timezone))
    # Quota guard — raises QuotaExceededError (429) before streaming begins.
    check_quota(user_id=uid, tier=ctx.tier, repo=repo)

    # Resolve or create the conversation row before streaming so the row always exists (no orphaned messages) and thread_id is stable.
    conversation_id = _open_conversation(repo, body, uid)
    thread_id = _thread_id(uid, body.trip_id, conversation_id)
    if body.resume is not None:
        await _require_pending_interrupt(
            graph, {"configurable": {"thread_id": thread_id}}
        )

    # record_agent_run finalizes the row once the SSE stream drains.
    run_id = str(uuid4())
    # persist_assistant_turn stores the reply under this id and echoes it on `done`.
    assistant_message_id = str(uuid4())
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
        stream_input = Command(resume=body.resume)
    else:
        safe_message = redact_pii(body.message)
        # Persist the user turn before streaming so the row survives an abandoned stream; skip on retry (already saved) to avoid a duplicate bubble.
        if not body.retry:
            repo.append_message(
                conversation_id=conversation_id, role="user", content=safe_message
            )
        stream_input = _turn_input(safe_message, uid, body.trip_id, auth_user.email)

    # Commit before streaming so the isolated factory session inside persist_assistant_turn can write (SQLite: prevents "database is locked").
    session.commit()

    factory = _isolated_factory(session)

    # Populated by stream_agent_events after the SSE stream drains; read by the background task below so memory extraction runs off the reply path.
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
                prompt_versions=getattr(graph, "prompt_versions", None),
            ),
            conversation_id=conversation_id,
            session_factory=factory,
            run_id=run_id,
            message_id=assistant_message_id,
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
    """Return all conversations for the authenticated user, newest first; the ``user_id`` query param is deprecated and ignored (identity is the JWT sub, no enumeration)."""
    uid = auth_user.id
    repo = ConversationRepository(session)
    return repo.list_for_user(uid)


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=ConversationMessages,
    summary="List messages for a conversation",
)
async def list_conversation_messages(
    conversation_id: str,
    graph: GraphOptionalDep,
    session: SessionDep,
    auth_user: CurrentUserDep,
    user_id: str | None = None,
) -> ConversationMessages:
    """Return a conversation's messages (oldest first) plus any pending HITL interrupt state.

    Ownership-scoped: an unknown or non-owned conversation returns empty, neither leaking contents nor confirming existence. Uses ``GraphOptionalDep`` so a down/not-yet-built graph degrades to ``interrupt_pending=False`` instead of failing this pure-DB read.
    """
    uid = auth_user.id
    repo = ConversationRepository(session)
    conversation = repo.get(conversation_id)
    if conversation is None or conversation.user_id != uid:
        return ConversationMessages(messages=[])

    interrupt_pending = False
    interrupt_payload = None
    if graph is not None:
        thread_id = _thread_id(uid, conversation.trip_id, conversation_id)
        cfg = {"configurable": {"thread_id": thread_id}}
        try:
            state = await graph.aget_state(cfg)
            interrupt_pending = bool(state.interrupts)
            interrupt_payload = state.interrupts[0].value if state.interrupts else None
        except Exception:  # noqa: BLE001 — best-effort; the message history below still returns
            pass
    messages = repo.list_messages(conversation_id)
    # One bulk fold + one bulk run-status lookup for the assistant messages, never per message.
    assistant_ids = [m.id for m in messages if m.role == MessageRole.ASSISTANT]
    feedback = FeedbackRepository(session).effective_for(assistant_ids)
    run_status = repo.run_status_for_messages(assistant_ids)
    for m in messages:
        m.feedback = feedback.get(m.id)
        run_id, status = run_status.get(m.id, (None, None))
        m.rateable = is_rateable(m.role, run_id, status)
    return ConversationMessages(
        messages=messages,
        interrupt_pending=interrupt_pending,
        interrupt_payload=interrupt_payload,
    )


@router.get(
    "/manifest", response_model=AgentManifest, summary="Agent capability manifest"
)
def agent_manifest() -> AgentManifest:
    """Get the agent capability manifest."""
    tools = [
        ToolManifestEntry(
            name=t.name,
            description=(t.description or "").strip().split("\n")[0],
            read_only=TOOL_METADATA[t.name]["readOnly"],
            destructive=TOOL_METADATA[t.name]["destructive"],
        )
        for t in ALL_TOOLS
    ]
    # The research launcher is declared only when its kill switch is on, mirroring
    # main.py wiring the routes on the same flag: with research_enabled false the
    # whole surface is invisible and /agent/manifest stays byte-identical to before
    # the feature (design §12.2/§12.3); once 7.2 flips the flag, a reachable premium
    # capability is honestly declared instead of silently omitted.
    subagents = [
        s for s in SUBAGENTS if s != "research" or get_settings().research_enabled
    ]
    return AgentManifest(subagents=subagents, tools=tools)


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
    """Reassign conversations from an anonymous id to the authenticated user; 403 if the source id is a registered account (prevents history theft)."""
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
