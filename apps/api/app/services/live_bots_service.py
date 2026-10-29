"""Pure mapping of ``agent_runs`` rows onto the live-bots DTO (no DB access).

Rows are duck-typed (``AgentRun`` / ``AgentRunStep`` or any object with the same
attributes) so every function here is unit-testable without a database. The DTO
never carries a user id or email: only a short one-way label.
"""

import hashlib
from datetime import datetime

#: Specialist flows that get their own mascot; ``research`` comes from the research channel.
BOT_KINDS = frozenset({"planner", "concierge", "journal", "booking", "budget"})
GENERIC_BOT = "generic"

#: Seconds a finished run stays listed so its bot can play the "done" moment.
RECENT_FINISH_S = 8

#: ``agent_run_steps.error_type`` values (exception class names) that mean a transient failure the graph retries.
RETRYABLE_ERROR_TYPES = frozenset(
    {
        "APIConnectionError",
        "APITimeoutError",
        "APIConnectionTimeoutError",
        "RateLimitError",
        "InternalServerError",
        "TimeoutException",
        "ReadTimeout",
        "ConnectTimeout",
        "ConnectError",
        "ConnectionError",
        "UpstreamError",
    }
)

_CLASSIFY_NODES = frozenset(
    {"pii_guardrail", "load_context", "summarize", "supervisor", "route_tasks", "plan"}
)


def bot_kind(current_flow: str | None, channel: str | None) -> str:
    """Mascot kind: the research channel wins, then a known specialist flow, else ``generic``."""
    if channel == "research":
        return "research"
    if current_flow in BOT_KINDS:
        return current_flow
    return GENERIC_BOT


def stage(step_node: str | None) -> int:
    """0 classify, 1 specialist, 2 tools, 3 reflection; no step yet means still classifying."""
    if not step_node or step_node in _CLASSIFY_NODES:
        return 0
    if step_node == "reflection":
        return 3
    if step_node == "tools":
        return 2
    return 1


def state(status: str, step_status: str | None, step_error_type: str | None) -> str:
    """``running`` / ``waiting`` / ``retrying`` / ``done`` / ``failed``."""
    if status == "completed":
        return "done"
    if status == "failed":
        return "failed"
    if status == "interrupted":
        return "waiting"
    if step_status == "error" and step_error_type in RETRYABLE_ERROR_TYPES:
        return "retrying"
    return "running"


def user_label(user_id: str) -> str:
    """Short anonymous label (``user-1a2b``) from a one-way hash; never reveals the id or email."""
    digest = hashlib.sha256(user_id.encode()).hexdigest()
    return f"user-{digest[:4]}"


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


def elapsed_s(run, now: datetime) -> int:
    """Seconds since start (to ``finished_at`` once finished); 0 when the start is unknown."""
    started = _parse(run.started_at)
    if started is None:
        return 0
    end = _parse(run.finished_at) if run.status in ("completed", "failed") else None
    return max(0, int(((end or now) - started).total_seconds()))


def to_bot(run, step, now: datetime, stale_after_s: int) -> dict:
    """One bot DTO from a run row and its latest step (``None`` when no step is recorded)."""
    node = step.node if step is not None else None
    elapsed = elapsed_s(run, now)
    return {
        "id": run.id,
        "bot": bot_kind(run.current_flow, run.channel),
        "state": state(
            run.status,
            step.status if step is not None else None,
            step.error_type if step is not None else None,
        ),
        "stage": stage(node),
        "step": (step.tool_name or node) if step is not None else None,
        "elapsed_s": elapsed,
        "tokens": (run.input_tokens or 0) + (run.output_tokens or 0),
        "llm_calls": run.llm_calls or 0,
        "user": user_label(run.user_id),
        "channel": run.channel,
        "stale": run.status == "running" and elapsed > stale_after_s,
    }


def counts(bots: list[dict], done_today: int) -> dict:
    """Header counters; ``done_today`` comes from the DB since finished bots age out of the list."""
    return {
        "running": sum(1 for b in bots if b["state"] == "running"),
        "waiting": sum(1 for b in bots if b["state"] == "waiting"),
        "retrying": sum(1 for b in bots if b["state"] == "retrying"),
        "done_today": done_today,
    }
