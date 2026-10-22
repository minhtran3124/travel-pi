"""A/B probe: do the date-grounding rules still hold after moving the note to the end?

Run with CWD = <checkout>/apps/api so `app` and `eval` import from THAT checkout's code.
Reuses the eval harness's production runner (DB agent config, premium context), so each
turn is a real graph turn on the model that serves traffic.

Rules under test, verbatim intent from ground_current_date's note:
  NO-DATE  "If the traveller mentioned NO date at all, you MUST ask which date they want
            — never fall back to <today>, and never invent a date they did not give."
  RELATIVE "Resolve relative ... dates with the resolve_date tool — do not compute them."

Mechanical verdict per run (no judge):
  NO-DATE  VIOLATION if any search tool received a date (the traveller gave none, so any
           date is invented). Records whether the invented date equals today.
  RELATIVE VIOLATION if a dated search ran without a resolve_date call in the same turn.
"""
import json, sys, datetime as dt
from app.core.config import get_settings
from app.db.engine import get_session_factory
from eval.__main__ import _prod_agent_context
from eval.adapters.langgraph_runner import LangGraphRunner
from evalkit.types import Golden

K = int(sys.argv[1]); LABEL = sys.argv[2]; OUT = sys.argv[3]
PROBES = [
    ("N1", "no_date", "en", ["Find me a flight from Hanoi to Singapore."]),
    ("N2", "no_date", "vi", ["Tìm giúp tôi chuyến bay từ Hà Nội đi Đà Nẵng."]),
    ("N3", "no_date", "en", ["I'm planning a family trip to Singapore. We like morning flights and budget airlines.",
                             "Find me a flight there from Hanoi."]),
    ("R1", "relative", "en", ["Find me a flight from Hanoi to Tokyo next Friday."]),
]
DATE_ARGS = {"search_flights": ("departure_date",), "search_hotels": ("check_in", "check_out")}
today = dt.datetime.now(dt.timezone.utc).date().isoformat()
runner = LangGraphRunner(context=_prod_agent_context(get_session_factory(get_settings().database_url)))
rows = []
for pid, kind, lang, turns in PROBES:
    for i in range(K):
        g = Golden(id=f"daterule-{pid}-{i}", capability="dates", scenario=kind, language=lang,
                   suite="full", turns=turns if len(turns) > 1 else None,
                   input=turns[0] if len(turns) == 1 else None)
        try:
            tr = runner.run(g)
        except Exception as exc:  # a crashed run is recorded, never silently dropped
            rows.append({"probe": pid, "kind": kind, "i": i, "error": f"{type(exc).__name__}: {exc}"[:200]}); continue
        dated = [(c.name, a, c.args.get(a)) for c in tr.tool_calls for a in DATE_ARGS.get(c.name, ()) if c.args.get(a)]
        used_resolve = any(c.name == "resolve_date" for c in tr.tool_calls)
        asked = any(c.name == "needs_clarification" for c in tr.tool_calls) or "?" in (tr.reply or "")
        if kind == "no_date":
            violation = bool(dated)
        else:
            violation = bool(dated) and not used_resolve
        rows.append({"probe": pid, "kind": kind, "i": i, "violation": violation,
                     "dated_args": dated, "fell_back_to_today": any(v == today for *_, v in dated),
                     "used_resolve_date": used_resolve, "asked": asked,
                     "tools": [c.name for c in tr.tool_calls], "reply_head": (tr.reply or "")[:140]})
        r = rows[-1]; print(f"[{LABEL}] {pid} #{i} violation={r['violation']} resolve={used_resolve} asked={asked} dated={dated}", flush=True)
json.dump({"label": LABEL, "today": today, "k": K, "rows": rows}, open(OUT, "w"), indent=2, ensure_ascii=False)
bad = sum(1 for r in rows if r.get("violation")); err = sum(1 for r in rows if "error" in r)
print(f"[{LABEL}] DONE runs={len(rows)} violations={bad} errors={err} -> {OUT}", flush=True)
