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
from app.research.tools import MAIN_TOOLS, SUBAGENT_TOOLS
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
            # Errors outermost: an ids pass only ever sees a successful result.
            middleware=[
                TodoListMiddleware(),
                _ToolErrorsToMessages(),
                _ToolIdsToContent(),
            ],
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


def _price(
    amount: object,
    currency: object,
) -> str:
    return f"{currency} {float(amount):.0f}" if amount is not None else ""


def _place_line(p: dict) -> str:
    return f"- {p.get('name')} ({p.get('category')}) → place_id {p['id']}"


def _flight_line(f: dict) -> str:
    departs = str(f.get("departure_time", "")).replace("T", " ")[:16]
    return (
        f"- {f.get('flight_number')} {f.get('origin')}→{f.get('destination')} "
        f"{departs}, {_price(f.get('price'), f.get('currency'))} → offer_id {f['id']}"
    )


def _hotel_line(h: dict) -> str:
    availability = "available" if h.get("available", True) else "sold out"
    return (
        f"- {h.get('name')} ({h.get('star_rating')}★, "
        f"{_price(h.get('price_per_night'), h.get('currency'))}/night, {availability}) "
        f"→ hotel_id {h['id']}"
    )


#: Panel kind → (list key in the panel data, one line per item). Kept to the panels
#: whose items the proposal cites; ``nearby_places`` / ``resolve_place`` already
#: return whole objects, ids included.
_ID_PANELS = {
    "places": ("places", _place_line),
    "flights": ("flights", _flight_line),
    "hotels": ("hotels", _hotel_line),
}


class _ToolIdsToContent(AgentMiddleware):
    """Append the ids the proposal must cite to what the research model reads.

    The shared chat tools keep ids in the side-panel ``artifact`` and show the model
    only names and flight numbers, so a live run could not cite a single real
    ``place_id`` / ``hotel_id`` and put flight numbers where ``offer_id``s belong.
    Adding them here leaves the tools — and the chat and MCP output — unchanged.
    """

    @staticmethod
    def _with_ids(result):
        if not isinstance(result, ToolMessage) or result.status == "error":
            return result
        artifact = result.artifact
        if not isinstance(artifact, dict) or artifact.get("kind") not in _ID_PANELS:
            return result
        key, line = _ID_PANELS[artifact["kind"]]
        items = [
            item
            for item in (artifact.get("data") or {}).get(key) or []
            if isinstance(item, dict) and item.get("id")
        ]
        if not items:
            return result
        ids = "\n".join(line(item) for item in items)
        content = (
            f"{result.content}\n\nIds for the proposal — cite these exactly, "
            f"never a name or flight number:\n{ids}"
        )
        return result.model_copy(update={"content": content})

    def wrap_tool_call(self, request, handler):
        return self._with_ids(handler(request))

    async def awrap_tool_call(self, request, handler):
        return self._with_ids(await handler(request))


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
        tools=MAIN_TOOLS,
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
