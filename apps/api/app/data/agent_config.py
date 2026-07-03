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

# One-line role description per node, shown on the config card so the grid reads
# at a glance. Sourced from each node's active prompt (``app/prompts/<name>``).
# Static metadata (like the group titles/blurbs above) — not a per-row DB
# override, so it needs no migration and can't drift between agents.
AGENT_DESCRIPTIONS: dict[str, str] = {
    "supervisor": "Reads each turn and routes it to the right specialist.",
    "planner": "Builds and edits the traveller's itinerary and daily plan.",
    "concierge": "Answers travel questions with local recommendations and tips.",
    "journal": "Logs trip events and keeps the itinerary up to date.",
    "booking": "Quotes and confirms flights, hotels, and activities.",
    "budget": "Records expenses and reports on the trip budget.",
    "summarize": "Condenses long conversations to keep the context small.",
    "reflection": "Reviews the last answer and asks for a fix when it's weak.",
    "extract_memory": "Saves durable traveller preferences to long-term memory.",
}
