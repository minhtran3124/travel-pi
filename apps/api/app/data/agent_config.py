"""Single source of truth for the LLM node names seeded into ``agent_config``.

Nodes are grouped for the config dashboard: the main supervisor, the domain
sub-agents it delegates to, and the support nodes (memory / summarization /
reflection). ``AGENT_CONFIG_NODES`` is *derived* from the groups so seeding and
the UI share one source of truth.
"""

# (section title, one-line blurb, [node name, ...])
AGENT_CONFIG_GROUPS: list[tuple[str, str, list[str]]] = [
    (
        "Main agent",
        "The supervisor that reads each turn and routes it to a specialist.",
        ["supervisor"],
    ),
    (
        "Domain sub-agents",
        "ReAct specialists the supervisor delegates a task to.",
        ["planner", "concierge", "journal", "booking", "budget"],
    ),
    (
        "Support agents",
        "Background nodes for memory, summarization and reflection.",
        ["summarize", "reflection", "extract_memory"],
    ),
]

AGENT_CONFIG_NODES: list[str] = [
    name for _title, _blurb, names in AGENT_CONFIG_GROUPS for name in names
]
