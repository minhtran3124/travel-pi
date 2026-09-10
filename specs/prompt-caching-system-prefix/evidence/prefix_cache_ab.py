"""Before/after measurement of the ONE thing design D1 changes: whether the agent system prompt's
cacheable prefix survives a change of the date note (a different timezone or a new day).

Run with CWD = <checkout>/apps/api so the prompt is assembled by THAT checkout's real code
(`build_subagent` → system_with_summary → with_reply_language → ground_current_date, in whichever
order the checkout has). The system message is captured exactly as the model would receive it.

Per timezone pair (A, B): send the tz-A prompt (warm), then the tz-B prompt, and read OpenAI's
`cached_tokens` on the tz-B call. That is the number of leading tokens the two prompts share and
the cache served. Note-first code differs from byte 0, so it should be ~0; note-last code shares
everything before the note. Pairs use unusual zones so no earlier traffic could have warmed a
note-first prefix.
"""
import json, sys
from langchain_core.messages import HumanMessage
from app.agents.context import AgentContext
from app.agents.subagents._base import build_subagent
from app.clients.llm import FakeLLM, _build_chat_model
from app.prompts.registry import registry

LABEL, OUT = sys.argv[1], sys.argv[2]
PAIRS = [("Pacific/Chatham", "Pacific/Kiritimati"), ("Atlantic/Azores", "Asia/Kathmandu")]
STATE = {"messages": [HumanMessage(content="Find me a flight to Tokyo next Friday.")],
         "summary": "Traveller is planning a family trip to Japan in late September; prefers morning flights.",
         "language": "en"}

def system_for(tz):
    captured = {}
    class Capture(FakeLLM):
        def _generate(self, messages, *a, **k):
            captured["sys"] = messages[0].content
            return super()._generate(messages, *a, **k)
    agent = build_subagent("planner", [], lambda _: Capture(responses=["ok"]), registry.get("planner"))
    agent.invoke(dict(STATE), context=AgentContext(timezone=tz))
    return captured["sys"]

def shared_prefix_chars(a, b):
    n = 0
    for x, y in zip(a, b):
        if x != y: break
        n += 1
    return n

model = _build_chat_model("openai", "gpt-5.4-mini")
rows = []
for tz_a, tz_b in PAIRS:
    sa, sb = system_for(tz_a), system_for(tz_b)
    human = HumanMessage(content="Reply with the single word OK.")
    model.invoke([{"role": "system", "content": sa}, human])                   # warm tz-A
    r = model.invoke([{"role": "system", "content": sb}, human])               # measure tz-B
    u = r.usage_metadata or {}
    row = {"pair": [tz_a, tz_b], "system_chars": len(sb),
           "shared_prefix_chars": shared_prefix_chars(sa, sb),
           "note_position": "first" if sb.startswith("CURRENT DATE") else "last",
           "input_tokens": u.get("input_tokens"),
           "cached_tokens": (u.get("input_token_details") or {}).get("cache_read", 0)}
    rows.append(row)
    print(f"[{LABEL}] {tz_a}->{tz_b} note={row['note_position']} shared_prefix={row['shared_prefix_chars']}/{row['system_chars']} chars  "
          f"input={row['input_tokens']} cached={row['cached_tokens']}", flush=True)
json.dump({"label": LABEL, "rows": rows}, open(OUT, "w"), indent=2)
