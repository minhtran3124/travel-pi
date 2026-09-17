"""Static node -> prompt attribution for the per-step call chain.

The map is keyed on the same ``"<ns_root>/<node>"`` form ``metrics._node_key``
produces: every sub-agent's inner node is called ``assistant``, so keying on the
bare name would collapse all five onto one key. A ``synthesis_worker`` step carries
its specialist by metadata (the namespace has none), and ``prompts_for`` re-keys it.
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
        # Outer node span carries the same attribution its inner ``assistant`` composes.
        entries[name] = list(prompts)
        for inner in _SUBGRAPH_NODES:
            # Only ``assistant`` builds a system message; ``tools``/``trip_guard`` run no model.
            entries[f"{name}/{inner}"] = list(prompts) if inner == "assistant" else []
    # The specialist appears nowhere in a worker's namespace, so its keys stay empty;
    # a step carrying a ``specialist`` is re-keyed by ``prompts_for``.
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
    """Return ``{prompt_name: active_version}`` for every registered prompt."""
    return {name: registry.active_version(name) for name in registry.names()}


def _attribution_key(node_key: str, specialist: str | None) -> str:
    """The map key a step is attributed under; a worker's ``assistant`` step is
    re-keyed onto ``"<specialist>/assistant"``, which the node key cannot express."""
    if specialist and node_key.endswith("/assistant"):
        return f"{specialist}/assistant"
    return node_key


def prompts_for(
    node_key: str, snapshot: dict[str, int], specialist: str | None = None
) -> list[dict[str, Any]]:
    """Return the prompt pointers for one node key; empty when it builds no prompt."""
    return [
        {"name": name, "version": snapshot.get(name)}
        for name in PROMPTS_FOR_NODE.get(_attribution_key(node_key, specialist), ())
    ]


def enrich_steps(
    steps: list[dict[str, Any]], snapshot: dict[str, int] | None
) -> list[dict[str, Any]]:
    """Attach ``prompts`` and ``cost_usd`` to a ``TurnMetricsHandler.steps()`` list.

    Shared by both persistence sites so the two channels store identical rows.
    """
    enriched: list[dict[str, Any]] = []
    for step in steps:
        row = dict(step)
        node = row.get("node")
        if node and snapshot:
            row["prompts"] = prompts_for(
                _node_key(node, row.get("ns") or ""),
                snapshot,
                row.get("specialist"),
            )
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
