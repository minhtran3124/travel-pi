"""Static node -> prompt attribution for the per-step call chain.

A trace step records *which prompts composed the system message* for the node
that produced it, as ``[{"name", "version"}]`` pointers into the on-disk prompt
registry (``app/prompts/<name>/v<N>.md``) rather than the prose itself — see
``specs/agent-run-trace-detail/design.md`` §3 and §4.2.

Two independent pieces:

* :data:`PROMPTS_FOR_NODE` — the static map, keyed on the *same* form
  ``app.agents.metrics._node_key`` produces (``"<ns_root>/<node>"`` inside a
  sub-graph, else the bare node name). Keying on the bare node name would be
  wrong: every sub-agent's inner node is literally called ``assistant``
  (``subagents/_base.py``), so all five would collapse onto one key. Identity
  survives only in the checkpoint namespace, hence ``planner/assistant``,
  ``concierge/assistant``, ….
* :func:`prompt_versions_snapshot` — ``{name: active_version}`` for every
  registered prompt, taken **at graph build** (the sub-agent prompts are read
  once when the graph is compiled, so a later ``active.yaml`` edit does not
  change the running graph).

``synthesis_worker`` picks its specialist from ``state["task"]`` at runtime. The
specialist name *is* present in the checkpoint namespace, but ``_node_key`` keeps
only the namespace root (the worker), so it does not reach this map and those
inner nodes map to ``[]``. Recovering it means reading the middle namespace
segment — a follow-up, noted because this is the busiest LLM path.
``summarize`` and ``synthesize`` build their system text outside the registry.
"""

from __future__ import annotations

from typing import Any

from app.agents.constants import ALL_SUBAGENTS
from app.agents.metrics import _node_key
from app.core.pricing import estimate_cost

_STYLE = "communication_style"

# Inner node names of a sub-agent ReAct sub-graph (``subagents/_base.py``).
_SUBGRAPH_NODES = ("assistant", "tools", "trip_guard")


def _subagent_entries() -> dict[str, list[str]]:
    """Build the sub-agent portion of the map (outer node + its inner nodes)."""
    entries: dict[str, list[str]] = {}
    for name in ALL_SUBAGENTS:
        prompts = [name, _STYLE]
        # The outer sub-graph node span covers the same prompts its inner
        # ``assistant`` composes, so both carry the attribution.
        entries[name] = list(prompts)
        for inner in _SUBGRAPH_NODES:
            # Only ``assistant`` builds a system message; ``tools`` /
            # ``trip_guard`` run no model.
            entries[f"{name}/{inner}"] = list(prompts) if inner == "assistant" else []
    # ``synthesis_worker`` invokes one of these sub-graphs inside its own node, so
    # the namespace root is the worker rather than the specialist. The specialist
    # is still in the middle namespace segment; ``_node_key`` just discards it, so
    # attribution is recoverable later but not available from this key today.
    for inner in _SUBGRAPH_NODES:
        entries[f"synthesis_worker/{inner}"] = []
    return entries


PROMPTS_FOR_NODE: dict[str, list[str]] = {
    # Root nodes that build a registry prompt.
    "supervisor": ["supervisor"],
    "reflection": ["reflection"],
    # Root nodes that build no registry prompt.
    "pii_guardrail": [],
    "load_context": [],
    "plan": [],
    "summarize": [],
    "synthesize": [],
    "synthesis_worker": [],
    **_subagent_entries(),
}


def prompt_versions_snapshot(registry: Any) -> dict[str, int]:
    """Return ``{prompt_name: active_version}`` for every registered prompt.

    :param registry: A ``PromptRegistry`` (``names()`` + ``active_version()``).
    :return: The active version of every known prompt name.
    """
    return {name: registry.active_version(name) for name in registry.names()}


def prompts_for(node_key: str, snapshot: dict[str, int]) -> list[dict[str, Any]]:
    """Return the prompt pointers for one node key.

    :param node_key: A ``metrics._node_key`` value (``"planner/assistant"``, …).
    :param snapshot: A :func:`prompt_versions_snapshot` result.
    :return: ``[{"name", "version"}]``; empty when the node builds no registry
        prompt or the key is unknown.
    """
    return [
        {"name": name, "version": snapshot.get(name)}
        for name in PROMPTS_FOR_NODE.get(node_key, ())
    ]


def enrich_steps(
    steps: list[dict[str, Any]], snapshot: dict[str, int] | None
) -> list[dict[str, Any]]:
    """Attach ``prompts`` and ``cost_usd`` to a ``TurnMetricsHandler.steps()`` list.

    Shared by both persistence sites (``agent_chat._finalize`` and
    ``record_agent_run``'s finalizer) so the two channels store identical rows.
    The node key is rebuilt exactly as ``metrics._node_key`` does, from the step's
    own ``node`` + ``ns``.

    :param steps: Step dicts as returned by ``TurnMetricsHandler.steps()``.
    :param snapshot: A :func:`prompt_versions_snapshot` result, or ``None`` when
        the graph exposes none (then every step gets ``prompts = []``).
    :return: New step dicts with ``prompts`` and ``cost_usd`` filled in.
    """
    enriched: list[dict[str, Any]] = []
    for step in steps:
        row = dict(step)
        node = row.get("node")
        if node and snapshot:
            row["prompts"] = prompts_for(_node_key(node, row.get("ns") or ""), snapshot)
        else:
            row["prompts"] = []
        model = row.get("model")
        if row.get("kind") == "llm" and model:
            row["cost_usd"] = estimate_cost(
                {
                    model: {
                        "input_tokens": row.get("input_tokens", 0),
                        "output_tokens": row.get("output_tokens", 0),
                        "cached_tokens": row.get("cached_tokens", 0),
                    }
                }
            )
        else:
            row["cost_usd"] = None
        enriched.append(row)
    return enriched
