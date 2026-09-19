"""The trip-research deep agent (`deepagents.create_deep_agent`).

A second, independent graph beside the chat graph (design §1–§3). It binds the registry's
read-only tools unchanged, routes its dossier / memory / skills through a `CompositeBackend`,
delegates each research dimension to an isolated subagent, and self-checks the proposal with
a rubric grader. Nothing here is wired into a router or lifespan — that is a later wave.
"""

from __future__ import annotations

import logging
from pathlib import Path

from deepagents import (
    FilesystemPermission,
    GeneralPurposeSubagentProfile,
    HarnessProfile,
    RubricMiddleware,
    SubAgent,
    create_deep_agent,
    register_harness_profile,
)
from deepagents.backends.composite import CompositeBackend
from deepagents.backends.state import StateBackend
from deepagents.backends.store import StoreBackend
from deepagents.middleware.filesystem import FilesystemBackend, FilesystemMiddleware
from langchain.agents.middleware import AgentMiddleware, TodoListMiddleware
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.store.base import BaseStore

from app.agents.retry import describe_tool_failure
from app.clients.llm import get_agent_llm
from app.prompts.registry import registry
from app.research.context import ResearchContext
from app.research.memory import GuardedStoreBackend
from app.research.state import ResearchState
from app.research.tools import SUBAGENT_TOOLS
from app.research.validate import make_validate_proposal

logger = logging.getLogger(__name__)

SKILLS_DIR = str(Path(__file__).resolve().parent / "skills")

# deepagents default is 9_999; the design caps the main agent (§8) via ``.with_config``.
AGENT_RECURSION_LIMIT = 150
# Design §8 also caps each subagent at 60. deepagents 0.7.15 exposes no declarative
# per-subagent recursion field on ``SubAgent``; a declarative subagent inherits the parent's
# ambient limit (150) through langgraph's per-key config merge. Binding 60 would require a
# ``CompiledSubAgent`` whose runnable is ``.with_config``-bound, which forfeits the
# profile-driven ``execute`` exclusion, skills, permissions and ``state_schema`` forwarding
# that the declarative path gives for free — so subagents are bounded at 150, not 60.

# Short, action-oriented delegation descriptions (design §3). Skills carry the methodology.
_SUBAGENT_DESCRIPTIONS: dict[str, str] = {
    "flights": "Research flight options and write /research/flights.md with cited offers.",
    "stays": "Research hotels and neighbourhoods and write /research/stays.md with cited ids.",
    "days": "Build day-by-day plans and write each /research/days/day-N.md with cited places.",
    "entry_season": "Research visa, entry rules, climate and packing into /research/entry-and-season.md.",
    "budget": "Estimate the trip budget from cited figures and write /research/budget.md.",
}


def _provider_key(model: BaseChatModel) -> str:
    """Return the harness-profile key for *model* — its ``ls_provider`` (e.g. ``openai``).

    The design names an "OpenAI" profile; keying off the model's own provider makes the
    profile apply to the real ``ChatOpenAI`` in production and to ``FakeLLM`` offline. A
    hardcoded ``"openai"`` would silently fail to match ``FakeLLM`` (provider ``fakellm``),
    leaving ``execute`` bound and the general-purpose subagent enabled.
    """
    try:
        params = model._get_ls_params()
    except (AttributeError, TypeError, NotImplementedError):
        return "openai"
    provider = params.get("ls_provider") if isinstance(params, dict) else None
    return provider or "openai"


def _register_profile(model: BaseChatModel) -> None:
    """Register the harness profile: drop ``execute`` and the general-purpose subagent.

    Idempotent — ``register_harness_profile`` merges on re-registration, so rebuilding the
    agent (lifespan config change) or building it per test never conflicts.
    """
    register_harness_profile(
        _provider_key(model),
        HarnessProfile(
            excluded_tools=frozenset({"execute"}),
            general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
        ),
    )


def _permissions() -> list[FilesystemPermission]:
    """Read anywhere; write only under the dossier, plan and memory routes (first match wins)."""
    return [
        FilesystemPermission(operations=["read"], paths=["/**"], mode="allow"),
        FilesystemPermission(
            operations=["write"],
            paths=["/research/**", "/plan/**", "/memory/**"],
            mode="allow",
        ),
        FilesystemPermission(operations=["write"], paths=["/**"], mode="deny"),
    ]


def _backend(store: BaseStore) -> CompositeBackend:
    """Route `/skills/` (read-only files), `/memory/` (guarded), `/research/` + `/plan/` (store)."""

    def research_ns(rt: object) -> tuple[str, ...]:
        return ("users", rt.context.user_id, "research", rt.context.trip_id)

    def memory_ns(rt: object) -> tuple[str, ...]:
        return ("users", rt.context.user_id, "research_memory")

    return CompositeBackend(
        default=StateBackend(),
        routes={
            "/skills/": FilesystemBackend(root_dir=SKILLS_DIR, virtual_mode=True),
            "/memory/": GuardedStoreBackend(store=store, namespace=memory_ns),
            "/research/": StoreBackend(store=store, namespace=research_ns),
            "/plan/": StoreBackend(store=store, namespace=research_ns),
        },
    )


def _subagents() -> list[SubAgent]:
    """One isolated subagent per research dimension, each with the skills route and a todo list."""
    return [
        SubAgent(
            name=name,
            description=_SUBAGENT_DESCRIPTIONS[name],
            tools=SUBAGENT_TOOLS[name],
            skills=["/skills/"],
            middleware=[TodoListMiddleware(), _ToolErrorsToMessages()],
        )
        for name in SUBAGENT_TOOLS
    ]


class _ToolErrorsToMessages(AgentMiddleware):
    """Turn a tool failure into a ToolMessage the model can read and recover from.

    Without this one ``ToolException`` ends the whole run: a research turn is minutes
    of work across five subagents, and the first ambiguous date or upstream hiccup
    threw all of it away (seen on a live run — ``resolve_date`` rejected a phrase and
    the turn died). The chat graph has handled this since #113; routing through
    :func:`describe_tool_failure` keeps ONE verdict per failure class instead of a
    second, drifting opinion here.

    Both halves are implemented on purpose: the runner drives the agent with
    ``astream_events`` while the offline tests drive it with ``invoke``, and a
    middleware that implements only one raises ``NotImplementedError`` on the other
    (the sync/async split in
    ``docs/solutions/agent/sync-node-breaks-async-only-tools.md``).
    """

    @staticmethod
    def _as_message(request, exc: Exception) -> ToolMessage:
        logger.warning(
            "[research] tool %s failed: %s",
            request.tool_call.get("name"),
            type(exc).__name__,
        )
        return ToolMessage(
            content=describe_tool_failure(exc),
            tool_call_id=request.tool_call["id"],
            name=request.tool_call.get("name"),
            status="error",
        )

    def wrap_tool_call(self, request, handler):
        try:
            return handler(request)
        except Exception as exc:  # noqa: BLE001 — breadth is the point, the verdict is not
            return self._as_message(request, exc)

    async def awrap_tool_call(self, request, handler):
        try:
            return await handler(request)
        except Exception as exc:  # noqa: BLE001 — breadth is the point, the verdict is not
            return self._as_message(request, exc)


def _read_file_tool(
    backend: CompositeBackend,
    permissions: list[FilesystemPermission],
) -> BaseTool:
    """The built-in ``read_file`` tool over *backend*, for the grader to open dossier files."""
    fs = FilesystemMiddleware(backend=backend, _permissions=permissions)
    return next(tool for tool in fs.tools if tool.name == "read_file")


def build_research_agent(
    *,
    store: BaseStore,
    checkpointer: BaseCheckpointSaver | None,
    llm: BaseChatModel | None = None,
    grader_llm: BaseChatModel | None = None,
) -> CompiledStateGraph:
    """Build the compiled trip-research deep agent (design §2).

    ``store`` and ``checkpointer`` are the process-lifetime instances shared with the chat
    graph. ``llm`` / ``grader_llm`` default to the seeded ``agent_config`` resolutions; tests
    pass a ``FakeLLM`` for each.
    """
    model = llm or get_agent_llm("trip_research")
    grader = grader_llm or get_agent_llm("trip_research_grader")
    _register_profile(model)

    permissions = _permissions()
    backend = _backend(store)
    validate_proposal = make_validate_proposal(backend)

    return create_deep_agent(
        model=model,
        tools=[],
        system_prompt=registry.get("trip_research"),
        skills=["/skills/"],
        memory=["/memory/AGENTS.md"],
        permissions=permissions,
        subagents=_subagents(),
        middleware=[
            TodoListMiddleware(),
            _ToolErrorsToMessages(),
            RubricMiddleware(
                model=grader,
                tools=[validate_proposal, _read_file_tool(backend, permissions)],
                max_iterations=2,
            ),
        ],
        backend=backend,
        context_schema=ResearchContext,
        state_schema=ResearchState,
        checkpointer=checkpointer,
        store=store,
        name="trip_research",
    ).with_config(recursion_limit=AGENT_RECURSION_LIMIT)
