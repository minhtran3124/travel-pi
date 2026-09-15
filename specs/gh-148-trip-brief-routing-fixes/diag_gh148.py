"""gh-148 diagnostic: re-run the two failing goldens once (no judge) and dump
per-turn replies plus the final state's language / trip_facts / flow."""
import os, sys
sys.path.insert(0, os.getcwd())
import eval.__main__ as em
from app.core.config import get_settings
from app.db.engine import get_session_factory
from evalkit.dataset import JsonDatasetStore
from evalkit.registry import list_metrics
from eval.adapters.config import DATASET_DIR, TAXONOMY
from eval.adapters.langgraph_runner import LangGraphRunner

import json

IDS = ["language-ambiguous-en-01", "memory-multi_turn-vi-04"]
# `--tally N`: run language-ambiguous-en-01 N times and write a pass tally (E002).
TALLY = int(sys.argv[sys.argv.index("--tally") + 1]) if "--tally" in sys.argv else 0
TALLY_OUT = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else None
store = JsonDatasetStore(DATASET_DIR, TAXONOMY, known_metrics=set(list_metrics()))
goldens = [g for g in store.load(suite="full") if g.id in IDS]
runner = LangGraphRunner(context=em._prod_agent_context(get_session_factory(get_settings().database_url)))
if TALLY:
    from evalkit.metrics.deterministic import _detect_language as detect_language  # noqa: E402

    g = next(x for x in goldens if x.id == "language-ambiguous-en-01")
    runs = []
    for i in range(TALLY):
        tr = runner.run(g)
        st = runner._graph.get_state({"configurable": {"thread_id": tr.meta["thread_id"]}}).values
        lang = detect_language(tr.reply)
        runs.append({"run": i + 1, "reply_language": lang, "state_language": st.get("language"),
                     "passed": lang == "en", "reply": tr.reply[:400]})
        print(f"run {i + 1}: reply_language={lang} state.language={st.get('language')}")
    with open(TALLY_OUT, "w", encoding="utf-8") as fh:
        json.dump({"golden_id": g.id, "runs": runs}, fh, ensure_ascii=False, indent=2)
    sys.exit(0)

for g in goldens:
    tr = runner.run(g)
    st = runner._graph.get_state({"configurable": {"thread_id": tr.meta["thread_id"]}}).values
    print("\n==========", g.id)
    print("turns:", g.turns or [g.input])
    print("flow:", tr.flow, "| tasks:", tr.meta.get("tasks"))
    print("state.language:", st.get("language"))
    print("state.trip_facts:", st.get("trip_facts"))
    ai = [m for m in tr.messages if m.get("type") in ("ai", "AIMessage") or m.get("role") == "assistant"]
    for i, m in enumerate(ai):
        c = m.get("content") if isinstance(m.get("content"), str) else str(m.get("content"))
        if c.strip():
            print(f"--- AI msg {i} ---\n{c[:1500]}")
