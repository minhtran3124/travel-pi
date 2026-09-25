"""Conversation driver: runs traveller personas against ``/agent/stream``.

`run_batch` seats up to ``parallel`` travellers at once (an `asyncio.Semaphore`),
drives each one turn-by-turn against the streaming chatbot, forwards lobby events
to the bus, and stops per the quota / error rules of design §5.6–§5.7 and §7.
The traveller's next line comes from ``claude_cli.run``; the bot's reply comes
from the SSE stream.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx

from sim import claude_cli
from sim.personas import Persona, traveller_system_prompt
from sim.sse import HttpStatusError, stream_turn, to_ui_events

logger = logging.getLogger(__name__)

TIMEZONE = "UTC"
TURN_TIMEOUT = 180
DEFAULT_CEILING = 0.85
_FINISHED = ("done", "max_turns", "bot_error", "driver_error")

TRAVELLER_SCHEMA = {
    "type": "object",
    "properties": {
        "message": {"type": "string"},
        "intent_done": {"type": "boolean"},
    },
    "required": ["message", "intent_done"],
}


@dataclass
class SessionResult:
    persona: Persona
    conversation_id: str | None
    status: str
    turns: list[dict] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    panels: list[dict] = field(default_factory=list)
    error: dict | None = None
    started_at: datetime | None = None
    usage: dict = field(default_factory=dict)


@dataclass
class BatchResult:
    sessions: list[SessionResult]
    status: str
    claude_calls: int


@dataclass
class _Ctx:
    ceiling: float
    stop_admission: bool = False
    abort: bool = False
    batch_status: str = "ok"
    claude_calls: int = 0


@dataclass
class _Turn:
    reply: str = ""
    interrupt: bool = False
    error: dict | None = None
    abort_status: str | None = None
    usage: dict | None = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _over_ceiling(
    quota: claude_cli.Quota | None,
    ceiling: float,
) -> bool:
    if quota is None:
        return False
    for value in (quota.five_hour, quota.seven_day):
        if value is not None and value >= ceiling:
            return True
    return False


def _add_usage(
    total: dict,
    delta: dict | None,
) -> None:
    if not isinstance(delta, dict):
        return
    for key, value in delta.items():
        if isinstance(value, (int, float)):
            total[key] = total.get(key, 0) + value


def _user_prompt(turns: list[dict]) -> str:
    if not turns:
        return "Start the conversation with the travel assistant."
    return "\n".join(f"{turn['role']}: {turn['text']}" for turn in turns)


async def _maybe_await(fn, *args):
    outcome = fn(*args)
    if asyncio.iscoroutine(outcome):
        return await outcome
    return outcome


async def _publish_quota(bus) -> None:
    quota = claude_cli.last_quota
    if quota is None:
        return
    await bus.publish(
        {
            "type": "quota",
            "persona_id": None,
            "five_hour": quota.five_hour,
            "seven_day": quota.seven_day,
            "resets_at": quota.resets_at,
        }
    )


async def _leave(
    bus,
    persona_id: str,
    reason: str,
) -> None:
    await bus.publish(
        {"type": "persona_leave", "persona_id": persona_id, "reason": reason}
    )


async def _stream_once(
    body: dict,
    persona: Persona,
    token: str,
    base_url: str,
    client: httpx.AsyncClient,
    bus,
    result: SessionResult,
) -> _Turn:
    turn = _Turn()
    tool_names: dict[str, str] = {}
    reply_parts: list[str] = []
    pid = persona.id
    try:
        async for ev in stream_turn(client, base_url, token, body):
            if ev.name == "start":
                result.conversation_id = (
                    ev.data.get("conversation_id") or result.conversation_id
                )
            elif ev.name == "token":
                reply_parts.append(ev.data.get("content", ""))
            elif ev.name == "reset":
                reply_parts.clear()
            elif ev.name == "tool_call":
                tool_id = ev.data.get("id")
                name = ev.data.get("name")
                if tool_id is not None:
                    tool_names[tool_id] = name
                if name is not None:
                    result.tools.append(name)
            elif ev.name == "panel":
                result.panels.append(ev.data)
            elif ev.name == "done":
                turn.usage = ev.data.get("usage")
            elif ev.name == "interrupt":
                payload = ev.data.get("payload") or {}
                if payload.get("type") == "plan_approval":
                    turn.interrupt = True
            elif ev.name == "error":
                # to_ui_events already publishes the matching bot_error below.
                turn.error = {
                    "code": ev.data.get("code"),
                    "message": ev.data.get("message"),
                }
            for ui in to_ui_events(pid, ev):
                if ui["type"] == "bot_tool" and ui.get("name") is None:
                    ui["name"] = tool_names.get(ui.get("id"))
                elif ui["type"] == "bot_done":
                    ui["reply"] = "".join(reply_parts)
                await bus.publish(ui)
    except HttpStatusError as exc:
        turn.reply = "".join(reply_parts)
        if exc.status == 401:
            turn.abort_status = "auth_misconfigured"
        elif exc.status == 429:
            turn.abort_status = "tier_misconfigured"
        else:
            turn.error = {
                "code": f"http_{exc.status}",
                "message": f"api-sim returned {exc.status}",
            }
            await _publish_bot_error(bus, pid, turn.error)
        return turn
    except httpx.HTTPError as exc:
        turn.reply = "".join(reply_parts)
        turn.error = {"code": "transport", "message": str(exc)}
        await _publish_bot_error(bus, pid, turn.error)
        return turn
    turn.reply = "".join(reply_parts)
    return turn


async def _publish_bot_error(
    bus,
    persona_id: str,
    error: dict,
) -> None:
    await bus.publish(
        {
            "type": "bot_error",
            "persona_id": persona_id,
            "code": error.get("code"),
            "message": error.get("message"),
        }
    )


async def _call_claude(
    ctx: _Ctx,
    system_prompt: str,
    user_prompt: str,
) -> dict:
    try:
        ctx.claude_calls += 1
        return await claude_cli.run(system_prompt, user_prompt, TRAVELLER_SCHEMA)
    except claude_cli.DriverError:
        ctx.claude_calls += 1
        return await claude_cli.run(system_prompt, user_prompt, TRAVELLER_SCHEMA)


async def _run_session(
    persona: Persona,
    base_url: str,
    keys,
    bus,
    client: httpx.AsyncClient,
    ctx: _Ctx,
    sem: asyncio.Semaphore,
    seats: deque[int],
    set_tier,
) -> SessionResult | None:
    result = SessionResult(persona=persona, conversation_id=None, status="quota")
    await bus.publish({"type": "persona_queue", "persona_id": persona.id})

    # Once the session has settled we publish its terminal persona_leave; the
    # flag guards the blanket handler so a failure there neither overwrites the
    # settled status with driver_error nor publishes a second leave.
    leave_started = False
    pending_return: SessionResult | None = result
    try:
        async with sem:
            if ctx.abort:
                await _leave(bus, persona.id, "aborted")
                return None
            if ctx.stop_admission or _over_ceiling(claude_cli.last_quota, ctx.ceiling):
                ctx.stop_admission = True
                ctx.batch_status = "quota"
                await _leave(bus, persona.id, "quota")
                return result

            seat = seats.popleft()
            result.started_at = _now()
            await bus.publish(
                {"type": "walk_to_desk", "persona_id": persona.id, "seat": seat}
            )
            try:
                await _converse(
                    persona, base_url, keys, bus, client, ctx, result, set_tier
                )
            finally:
                seats.append(seat)

        if ctx.abort and result.status not in _FINISHED:
            pending_return, reason = None, "aborted"
        else:
            pending_return, reason = result, result.status
        leave_started = True
        await _leave(bus, persona.id, reason)
        return pending_return
    except Exception as exc:  # noqa: BLE001 - one crash must not stop the batch
        if leave_started:
            # The session already settled; only the terminal leave failed.
            logger.exception("[sim.driver] persona_leave failed for %s", persona.id)
            return pending_return
        logger.exception("[sim.driver] session for %s failed", persona.id)
        result.status = "driver_error"
        result.error = {"code": "driver_error", "message": str(exc)}
        await _leave(bus, persona.id, "driver_error")
        return result


async def _converse(
    persona: Persona,
    base_url: str,
    keys,
    bus,
    client: httpx.AsyncClient,
    ctx: _Ctx,
    result: SessionResult,
    set_tier,
) -> None:
    system_prompt = traveller_system_prompt(persona)
    token = keys.token_for(persona.id)
    if set_tier is not None:
        try:
            await _maybe_await(set_tier, persona.id)
        except Exception:  # noqa: BLE001 - a tier-setup failure is an env error
            logger.exception("[sim.driver] set_tier failed for %s", persona.id)
            ctx.abort = True
            ctx.batch_status = "tier_misconfigured"
            return
    turns_taken = 0

    while turns_taken < persona.max_turns:
        if ctx.abort or ctx.stop_admission:
            return

        try:
            reply = await _call_claude(ctx, system_prompt, _user_prompt(result.turns))
        except claude_cli.QuotaExhausted:
            ctx.stop_admission = True
            ctx.batch_status = "quota"
            result.status = "quota"
            await _publish_quota(bus)
            return
        except claude_cli.DriverError:
            result.status = "driver_error"
            result.error = {"code": "driver_error", "message": "claude -p failed"}
            await _publish_quota(bus)
            return
        await _publish_quota(bus)

        message = str(reply.get("message", ""))
        if reply.get("intent_done"):
            result.status = "done"
            return

        result.turns.append({"role": "user", "text": message})
        await bus.publish(
            {"type": "user_say", "persona_id": persona.id, "text": message}
        )

        body = {"message": message, "timezone": TIMEZONE}
        if result.conversation_id:
            body["conversation_id"] = result.conversation_id

        try:
            turn = await asyncio.wait_for(
                _run_turn(persona, token, base_url, client, bus, result, body),
                TURN_TIMEOUT,
            )
        except TimeoutError:
            result.status = "bot_error"
            result.error = {"code": "turn_timeout", "message": "turn exceeded 180s"}
            await _publish_bot_error(bus, persona.id, result.error)
            return

        _add_usage(result.usage, turn.usage)

        if turn.abort_status is not None:
            ctx.abort = True
            ctx.batch_status = turn.abort_status
            return
        if turn.error is not None:
            result.status = "bot_error"
            result.error = turn.error
            return

        turns_taken += 1

    result.status = "max_turns"


async def _run_turn(
    persona: Persona,
    token: str,
    base_url: str,
    client: httpx.AsyncClient,
    bus,
    result: SessionResult,
    body: dict,
) -> _Turn:
    turn = await _stream_once(body, persona, token, base_url, client, bus, result)
    result.turns.append({"role": "bot", "text": turn.reply})
    if turn.abort_status is not None or turn.error is not None or not turn.interrupt:
        return turn

    approved = persona.will_book
    result.turns.append({"role": "user", "text": f"[resume approved={approved}]"})
    resume_body = {
        "conversation_id": result.conversation_id,
        "resume": {"approved": approved},
    }
    resumed = await _stream_once(
        resume_body, persona, token, base_url, client, bus, result
    )
    result.turns.append({"role": "bot", "text": resumed.reply})
    if resumed.usage is not None:
        merged = dict(turn.usage or {})
        _add_usage(merged, resumed.usage)
        turn.usage = merged
    turn.abort_status = resumed.abort_status or turn.abort_status
    turn.error = resumed.error or turn.error
    return turn


async def run_batch(
    personas: list[Persona],
    parallel: int,
    base_url: str,
    keys,
    bus,
    client: httpx.AsyncClient,
    set_tier,
) -> BatchResult:
    ceiling = float(os.environ.get("SIM_QUOTA_CEILING", str(DEFAULT_CEILING)))
    ctx = _Ctx(ceiling=ceiling)
    sem = asyncio.Semaphore(parallel)
    seats: deque[int] = deque(range(parallel))

    tasks = [
        asyncio.create_task(
            _run_session(
                persona, base_url, keys, bus, client, ctx, sem, seats, set_tier
            )
        )
        for persona in personas
    ]
    gathered = await asyncio.gather(*tasks, return_exceptions=True)
    for item in gathered:
        if isinstance(item, BaseException):
            logger.error("[sim.driver] session task raised", exc_info=item)
    sessions = [item for item in gathered if isinstance(item, SessionResult)]
    return BatchResult(
        sessions=sessions,
        status=ctx.batch_status,
        claude_calls=ctx.claude_calls,
    )
