"""A/B the MIN-59 runtime rubric grader against the MIN-58 offline eval set.

Runs every dataset case twice through the REAL graph — once with the grader off
(today's baseline: booking/concierge fall through to ``reflection``) and once with
it on — and measures the trade-off the MIN-59 prototype exists to answer:

- **quality**: the MIN-58 G-Eval rubrics, each scoring only the cases that declare
  it (``metrics`` field), plus a grounding rubric that — unlike MIN-58's
  ``no_hallucination`` — is given the run's own tool output as ``retrieval_context``
  so the judge can actually check whether a fact was invented;
- **latency**: wall-clock per case, per arm;
- **cost**: exact LLM call count per case, per arm, via a callback handler; plus the
  grader's own verdict and revise count, read from graph state (``grader_verdict`` /
  ``grader_iterations`` — the observable surface added for exactly this).

**Toggle lever.** The runtime lever is the DB row ``agent_config."grader".enabled``,
read by ``_resolve_context``. That path is HTTP-only: this harness invokes the compiled
graph directly and passes ``context=AgentContext(...)``, so the DB row has no effect
here. The arm is therefore set with ``AgentContext(allow_grader=...)`` — the same flag
the router would have produced, one layer down. Disabled mode still traverses the extra
``grader → reflection`` node hop (behavior-identical, trace-visible), so a small constant
latency offset in the OFF arm is expected and must not be misread as grader cost.

Usage (needs a real judge key; run from ``apps/api``):

    ../../.venv/bin/python -m eval.run_grader_ab            # full A/B + REPORT.md
    ../../.venv/bin/python -m eval.run_grader_ab --dry-run  # no judge, no report
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from dataclasses import dataclass, field
from typing import Any

from app.agents.context import AgentContext
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from eval.run_deepeval import has_real_openai_key

# Graded flows get a rubric; the rest are a control arm — they route to reflection in
# BOTH arms, so any score delta on them is judge noise, not grader effect.
GRADED_FLOWS = ("booking", "concierge")


class _LLMCallCounter(BaseCallbackHandler):
    """Counts chat-model invocations for one graph run (the cost unit that matters)."""

    def __init__(self) -> None:
        self.calls = 0

    def on_chat_model_start(self, serialized, messages, **kwargs) -> None:  # noqa: D102
        self.calls += 1

    def on_llm_start(self, serialized, prompts, **kwargs) -> None:  # noqa: D102
        self.calls += 1


@dataclass
class ArmResult:
    """One case run under one arm (grader on or off)."""

    reply: str
    tool_outputs: list[str]
    tools_called: list[str]
    current_flow: str | None
    llm_calls: int
    latency_s: float
    grader_verdict: str | None
    grader_iterations: int
    scores: dict[str, float] = field(default_factory=dict)


def _tool_outputs(messages: list[Any]) -> list[str]:
    return [m.content for m in messages if isinstance(m, ToolMessage) and m.content]


def _tools_called(messages: list[Any]) -> list[str]:
    names = []
    for m in messages:
        for tc in getattr(m, "tool_calls", None) or []:
            name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)
            if name:
                names.append(name)
    return names


def _final_reply(messages: list[Any]) -> str:
    ai = [m for m in messages if isinstance(m, AIMessage) and m.content]
    if not ai:
        return ""
    content = ai[-1].content
    if isinstance(content, str):
        return content
    return "".join(b.get("text", "") for b in content if isinstance(b, dict))


def run_arm(graph, case: dict, index: int, *, allow_grader: bool) -> ArmResult:
    """Invoke the graph once for *case* under one arm and capture the measurements."""
    counter = _LLMCallCounter()
    # A fresh thread id per (case, arm) — a reused thread replays stale turns.
    cfg = {
        "configurable": {"thread_id": f"ab-{'on' if allow_grader else 'off'}-{index}"},
        "callbacks": [counter],
    }
    started = time.perf_counter()
    out = graph.invoke(
        {
            "messages": [HumanMessage(content=case["input"])],
            "user_id": "eval-ab",
            "trip_id": None,
        },
        cfg,
        context=AgentContext(allow_grader=allow_grader),
    )
    latency = time.perf_counter() - started
    messages = out["messages"]
    return ArmResult(
        reply=_final_reply(messages),
        tool_outputs=_tool_outputs(messages),
        tools_called=_tools_called(messages),
        current_flow=out.get("current_flow"),
        llm_calls=counter.calls,
        latency_s=latency,
        grader_verdict=out.get("grader_verdict"),
        grader_iterations=out.get("grader_iterations") or 0,
    )


def _grounding_metric():
    """Grounding rubric that can actually see the tool output.

    MIN-58's ``no_hallucination`` judges INPUT + ACTUAL_OUTPUT only, so the judge has
    to guess what the tools returned. Feeding the run's own tool output as
    ``retrieval_context`` is what makes "did it invent this hotel?" answerable — and
    grounding is precisely the axis the grader is supposed to move.
    """
    from deepeval.metrics import GEval
    from deepeval.test_case import SingleTurnParams

    return GEval(
        name="Grounding (tool-grounded)",
        criteria=(
            "The retrieval context contains the exact output of the tools the assistant "
            "called. Penalize the actual output for every hotel name, place, price, "
            "rating, or time that does not appear in, or follow from, that context — "
            "those are invented. Do not penalize generic advice, offers to refine the "
            "search, or facts explicitly present in the context."
        ),
        evaluation_params=[
            SingleTurnParams.INPUT,
            SingleTurnParams.ACTUAL_OUTPUT,
            SingleTurnParams.RETRIEVAL_CONTEXT,
        ],
        threshold=0.7,
        model="gpt-4o-mini",
    )


def score_arm(case: dict, arm: ArmResult) -> dict[str, float]:
    """Score one arm's reply with the rubrics the case declares, plus grounding."""
    from deepeval.test_case import LLMTestCase

    from eval.metrics_geval import GEVAL_METRICS

    if not (arm.reply or "").strip():
        return {}  # GEval rejects an empty actual_output (HITL interrupt cases)

    test_case = LLMTestCase(
        input=case["input"],
        actual_output=arm.reply,
        retrieval_context=arm.tool_outputs or None,
    )

    scores: dict[str, float] = {}
    for key in case.get("metrics", []):
        factory = GEVAL_METRICS.get(key)
        if factory is None or key == "no_hallucination":
            continue  # superseded by the tool-grounded rubric below
        metric = factory()
        metric.measure(test_case)
        scores[key] = metric.score

    # Grounding only means something when the agent actually called a tool.
    if arm.tool_outputs:
        metric = _grounding_metric()
        metric.measure(test_case)
        scores["grounding"] = metric.score
    return scores


def _load_agent_config() -> None:
    """Populate ``AgentConfigCache`` from the DB, as ``lifespan`` does for the API.

    ``build_eval_graph`` resolves every node's model through ``get_agent_llm``, which
    reads this cache. In a standalone process the cache is empty, so every node would
    silently fall back to the env default model instead of its ``agent_config`` row —
    including ``grader``, whose whole point is to run on the cheap tier.
    """
    from app.core.agent_config_cache import AgentConfigCache, reload_from_db
    from app.core.config import get_settings
    from app.db.engine import get_session_factory

    settings = get_settings()
    factory = get_session_factory(settings.database_url)
    AgentConfigCache.configure(factory, settings.agent_config_cache_ttl_seconds)
    reload_from_db(factory)
    grader = AgentConfigCache.get("grader")
    print(f"[ab] grader model = {grader.model if grader else '(no row — env default)'}")


def _pct(on: float, off: float) -> str:
    if off == 0:
        return "n/a"
    return f"{(on - off) / off * 100:+.0f}%"


def _mean(xs: list[float]) -> float:
    return statistics.mean(xs) if xs else 0.0


def main() -> int:  # noqa: C901
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="run both arms, skip the judge"
    )
    parser.add_argument(
        "--limit", type=int, default=0, help="only the first N cases (smoke)"
    )
    parser.add_argument(
        "--out", default="../../specs/min-59-runtime-self-eval-loop/REPORT.md"
    )
    parser.add_argument(
        "--json-out",
        default="../../specs/min-59-runtime-self-eval-loop/ab-results.json",
    )
    parser.add_argument(
        "--from-json",
        metavar="PATH",
        help="rebuild the report from a saved results file (no agent, no judge, no cost)",
    )
    args = parser.parse_args()

    if args.from_json:
        _write_report(args.out, _rows_from_json(args.from_json), dry_run=False)
        print(f"[ab] rebuilt {args.out} from {args.from_json}")
        return 0

    if not args.dry_run and not has_real_openai_key():
        print("[ab] SKIP: no real OPENAI_API_KEY (judge) — set one, or pass --dry-run.")
        return 0

    _load_agent_config()

    from eval.harness import build_eval_graph
    from eval.loader import load_all

    graph = build_eval_graph()
    datasets = load_all()

    rows: list[dict[str, Any]] = []
    index = 0
    for name, items in datasets.items():
        for case in items:
            if args.limit and index >= args.limit:
                break
            index += 1
            print(f"[ab] {index:>2} {name:<14} {case['input'][:50]!r}", flush=True)
            off = run_arm(graph, case, index, allow_grader=False)
            on = run_arm(graph, case, index, allow_grader=True)
            if not args.dry_run:
                off.scores = score_arm(case, off)
                on.scores = score_arm(case, on)
            rows.append({"dataset": name, "case": case, "off": off, "on": on})
            print(
                f"     off: {off.llm_calls:>2} calls {off.latency_s:5.1f}s"
                f" | on: {on.llm_calls:>2} calls {on.latency_s:5.1f}s"
                f" verdict={on.grader_verdict} iters={on.grader_iterations}",
                flush=True,
            )

    _write_json(args.json_out, rows)
    _write_report(args.out, rows, dry_run=args.dry_run)
    print(f"[ab] wrote {args.out}")
    return 0


def _rows_from_json(path: str) -> list[dict]:
    """Rehydrate the row shape ``_write_report`` expects from a saved results file."""
    with open(path) as fh:
        payload = json.load(fh)
    rows = []
    for item in payload:
        arms = {}
        for arm in ("off", "on"):
            a = item[arm]
            arms[arm] = ArmResult(
                reply=a["reply"],
                tool_outputs=[],
                tools_called=a["tools_called"],
                current_flow=a["current_flow"],
                llm_calls=a["llm_calls"],
                latency_s=a["latency_s"],
                grader_verdict=a["grader_verdict"],
                grader_iterations=a["grader_iterations"],
                scores=a["scores"],
            )
        rows.append(
            {
                "dataset": item["dataset"],
                "case": {"input": item["input"]},
                "off": arms["off"],
                "on": arms["on"],
            }
        )
    return rows


def _write_json(path: str, rows: list[dict]) -> None:
    payload = [
        {
            "dataset": r["dataset"],
            "input": r["case"]["input"],
            "expected_flow": r["case"].get("expected_flow"),
            **{
                arm: {
                    "reply": r[arm].reply,
                    "tools_called": r[arm].tools_called,
                    "current_flow": r[arm].current_flow,
                    "llm_calls": r[arm].llm_calls,
                    "latency_s": round(r[arm].latency_s, 3),
                    "grader_verdict": r[arm].grader_verdict,
                    "grader_iterations": r[arm].grader_iterations,
                    "scores": r[arm].scores,
                }
                for arm in ("off", "on")
            },
        }
        for r in rows
    ]
    with open(path, "w") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)


def _write_report(path: str, rows: list[dict], *, dry_run: bool) -> None:
    graded = [r for r in rows if r["on"].current_flow in GRADED_FLOWS]
    control = [r for r in rows if r["on"].current_flow not in GRADED_FLOWS]

    triggered = [r for r in graded if (r["on"].grader_iterations or 0) > 0]
    verdicts: dict[str, int] = {}
    for r in graded:
        v = r["on"].grader_verdict or "none"
        verdicts[v] = verdicts.get(v, 0) + 1

    lat_off = _mean([r["off"].latency_s for r in graded])
    lat_on = _mean([r["on"].latency_s for r in graded])
    calls_off = _mean([r["off"].llm_calls for r in graded])
    calls_on = _mean([r["on"].llm_calls for r in graded])

    metric_keys = sorted(
        {k for r in rows for arm in ("off", "on") for k in r[arm].scores}
    )

    lines = [
        "# MIN-59 — Runtime Rubric Grader: latency / cost / quality trade-off",
        "",
        f"Generated by `eval/run_grader_ab.py` over the MIN-58 eval set "
        f"({len(rows)} cases: {len(graded)} graded, {len(control)} control).",
        "",
        "## Methodology",
        "",
        "- Each case runs **twice** through the real compiled graph, fresh `thread_id` per",
        "  (case, arm), grader **off** then **on**.",
        "- **Arm lever:** `AgentContext(allow_grader=...)`, passed directly to `graph.invoke`.",
        '  The production lever is the DB row `agent_config."grader".enabled`, but that is read',
        "  by `_resolve_context` on the HTTP path only — this harness invokes the graph directly,",
        "  so the DB row has no effect here. The flag is the same one the router would produce.",
        "- **OFF is not a no-op path:** it still traverses `sub-agent → grader → reflection`",
        "  (the grader delegates without calling its judge). A small constant offset in the OFF",
        "  arm is that extra node hop, not grader cost.",
        "- **Cost unit** = chat-model invocations, counted with a LangChain callback, not tokens.",
        "- **Quality** = MIN-58 G-Eval rubrics, each applied only to the cases that declare it",
        "  (`metrics` field). MIN-58's `no_hallucination` is **replaced** by a `grounding` rubric",
        "  that receives the run's own tool output as `retrieval_context` — without it the judge",
        "  cannot tell an invented hotel from a real one, which is the axis the grader moves.",
        "- Judge = `gpt-4o-mini`. Scores are LLM-judged and **not** perfectly reproducible;",
        "  single-run deltas on a 19-case set are directional, not statistically significant.",
        "",
        "## Results",
        "",
        "### Cost and latency (graded flows only)",
        "",
        "| Measure | Grader off | Grader on | Delta |",
        "| --- | --- | --- | --- |",
        f"| Mean LLM calls / turn | {calls_off:.2f} | {calls_on:.2f} | {_pct(calls_on, calls_off)} |",
        f"| Mean wall-clock / turn | {lat_off:.1f}s | {lat_on:.1f}s | {_pct(lat_on, lat_off)} |",
        "",
        f"**Revision-trigger rate:** {len(triggered)}/{len(graded)} graded turns "
        f"({(len(triggered) / len(graded) * 100) if graded else 0:.0f}%) had the grader ask for "
        "at least one revision.",
        "",
        "`needs_revision` is a **transient** verdict — it is the state that sends the sub-agent",
        "back for another draft, so it is never the verdict a turn *ends* on. The turn terminates",
        "on `satisfied`, `max_iterations_reached`, or `grader_error`. The revision-trigger rate",
        "above is therefore counted from `grader_iterations > 0`, not from the table below.",
        "",
        "**Verdict distribution (grader-on arm, graded flows):**",
        "",
        "| Verdict | Cases |",
        "| --- | --- |",
    ]
    for v, n in sorted(verdicts.items(), key=lambda kv: -kv[1]):
        lines.append(f"| `{v}` | {n} |")

    lines += ["", "### Quality (mean G-Eval score, higher is better)", ""]
    if dry_run:
        lines.append("_Dry run — no judge scores._")
    else:
        lines += [
            "| Rubric | n | Grader off | Grader on | Delta |",
            "| --- | --- | --- | --- | --- |",
        ]
        for key in metric_keys:
            offs = [r["off"].scores[key] for r in rows if key in r["off"].scores]
            ons = [r["on"].scores[key] for r in rows if key in r["on"].scores]
            n = min(len(offs), len(ons))
            if not n:
                continue
            lines.append(
                f"| `{key}` | {n} | {_mean(offs):.3f} | {_mean(ons):.3f} | "
                f"{_mean(ons) - _mean(offs):+.3f} |"
            )

        # The table above is NOT the effect size. Both arms re-run the agent, so a case
        # the grader never revised still produces a different reply (LLM sampling). Those
        # cases are the noise floor; only revised cases can carry a grader effect.
        lines += [
            "",
            "#### Signal vs noise: split by whether the grader actually revised",
            "",
            "A case with `grader_iterations = 0` was not touched by the grader — its arms differ",
            "only by resampling. Those deltas measure judge + model noise, and set the bar the",
            "revised-case deltas must clear to mean anything.",
            "",
            "| Rubric | Revised (n / mean Δ) | Not revised (n / mean Δ) |",
            "| --- | --- | --- |",
        ]
        for key in metric_keys:
            rev = [
                r["on"].scores[key] - r["off"].scores[key]
                for r in rows
                if key in r["on"].scores
                and key in r["off"].scores
                and (r["on"].grader_iterations or 0) > 0
            ]
            nor = [
                r["on"].scores[key] - r["off"].scores[key]
                for r in rows
                if key in r["on"].scores
                and key in r["off"].scores
                and (r["on"].grader_iterations or 0) == 0
            ]
            rs = f"{len(rev)} / {_mean(rev):+.3f}" if rev else "0 / —"
            ns = f"{len(nor)} / {_mean(nor):+.3f}" if nor else "0 / —"
            lines.append(f"| `{key}` | {rs} | {ns} |")

        floor = [
            abs(r["on"].scores[k] - r["off"].scores[k])
            for r in rows
            for k in metric_keys
            if k in r["on"].scores
            and k in r["off"].scores
            and (r["on"].grader_iterations or 0) == 0
        ]
        if floor:
            lines += [
                "",
                f"**Noise floor:** mean |Δ| on non-revised cases = **{_mean(floor):.3f}** "
                f"(n={len(floor)}, max={max(floor):.3f}).",
            ]

    lines += [
        "",
        "### Per-case detail (graded flows)",
        "",
        "| Case | Verdict | Iters | Calls off→on | Latency off→on |",
        "| --- | --- | --- | --- | --- |",
    ]
    for r in graded:
        inp = r["case"]["input"][:44].replace("|", "\\|")
        lines.append(
            f"| {inp} | `{r['on'].grader_verdict}` | {r['on'].grader_iterations} | "
            f"{r['off'].llm_calls}→{r['on'].llm_calls} | "
            f"{r['off'].latency_s:.1f}s→{r['on'].latency_s:.1f}s |"
        )

    lines += [
        "",
        "### Control (ungraded flows — planner)",
        "",
        "These route to `reflection` in both arms. Any delta here is judge noise and sets the",
        "noise floor for reading the graded-flow deltas above.",
        "",
        "| Case | Calls off→on | Latency off→on |",
        "| --- | --- | --- |",
    ]
    for r in control:
        inp = r["case"]["input"][:44].replace("|", "\\|")
        lines.append(
            f"| {inp} | {r['off'].llm_calls}→{r['on'].llm_calls} | "
            f"{r['off'].latency_s:.1f}s→{r['on'].latency_s:.1f}s |"
        )

    lines += [
        "",
        "<!-- HAND-WRITTEN BELOW. Re-running this script (or --from-json) OVERWRITES everything",
        "     from here down. Copy the two sections out before regenerating. -->",
        "",
        "## Grader false-positive spot-check",
        "",
        "_Manual read of the verdict vs the answer on revised cases — fill in after reading_",
        "_`ab-results.json` (each revised case's `off.reply` vs `on.reply`). A rising `grounding`_",
        "_score does NOT by itself mean a better answer: an agent that refuses to answer invents_",
        "_nothing and scores well. Check whether each revision kept the answer useful._",
        "",
        "## Recommendation",
        "",
        "_Fill in: expand to other flows, hold, or revise the rubric._",
        "",
    ]
    with open(path, "w") as fh:
        fh.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    sys.exit(main())
