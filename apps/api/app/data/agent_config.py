"""LLM node names seeded into ``agent_config``; ``AGENT_CONFIG_NODES`` is derived from the groups."""

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
        [
            "summarize",
            "reflection",
            "extract_memory",
            "date_resolution",
            "synthesize",
        ],
    ),
]

AGENT_CONFIG_NODES: list[str] = [
    name for _title, _blurb, names in AGENT_CONFIG_GROUPS for name in names
]

# Static metadata (not a per-row DB override, so no migration).
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
    "date_resolution": "Parses a traveller's date wording into a structured intent.",
    "synthesize": "Combines the parallel specialists' findings into one answer.",
}
