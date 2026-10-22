"""Deterministic tool-call trajectory metrics (agent-eval-pipeline task 2.2).

Wraps `agentevals` (https://github.com/langchain-ai/agentevals, MIT,
langchain-ai) — the library-level graph/tool trajectory matcher — over this
project's own types. No LLM judge here: this is phase-1's judge-free
trajectory layer (`design-portability.md` §"Path to MCP", research-brief
§3 L2). `agentevals` itself pulls in `langchain_core` at import time (it is
a normal runtime dependency of that library), which is fine — the
portability boundary (`tests/eval/test_boundary.py`) only bans `evalkit/`
modules *themselves* importing `app.`/`fastapi`/`sqlalchemy`/`langgraph`/
`langchain`; this module only ever does `import agentevals...`.

Only `Golden.expected_trajectory` (``list[str]`` of tool *names*, no args)
is compared against the tool calls actually made, extracted from
`Trace.messages`. Both sides are reduced to one synthetic single-tool-call
assistant message per tool call before being handed to agentevals — this
(a) makes "order" mean "tool-call order", not "raw message order" (dropping
interleaved human/system/tool-result messages and the final reply), (b)
splits any turn that made several parallel tool calls into individual
entries so a flat expected-name list stays comparable, and (c) makes
agentevals' `tool_args_match_mode="ignore"` the only sane choice, since
`expected_trajectory` carries no argument info to compare.

Naming gotcha, verified against the installed `agentevals==0.0.9` package
(not from memory — its mode semantics are easy to get backwards): this
module's own ``mode="subset"`` (the default; "the agent may legitimately
call extra tools") maps to agentevals' ``trajectory_match_mode="superset"``.
agentevals' *own* "subset" mode means the opposite — the actual trajectory
must not exceed the reference (extra calls FAIL) — which is not what a
travel agent doing legitimate extra lookups needs. Do not "simplify" this
mapping to look symmetric.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from agentevals.trajectory.match import create_trajectory_match_evaluator

from evalkit.ports import Oracle
from evalkit.registry import register_metric
from evalkit.types import CheckResult, Golden, Trace

# This evalkit's own mode vocabulary -> agentevals' `trajectory_match_mode`.
# See the naming-gotcha note in the module docstring: "subset" here is
# agentevals' "superset".
_MODE_TO_AGENTEVALS_MODE: dict[str, str] = {
    "strict": "strict",
    "unordered": "unordered",
    "subset": "superset",
}


def _extract_tool_call_names(messages: list[dict[str, Any]]) -> list[str]:
    """Ordered tool-call names made by the assistant across *messages*.

    Accepts both LangChain-style dicts (``{"type": "ai", "tool_calls": [...]}``,
    the shape `Trace.messages` is documented to carry) and OpenAI-style dicts
    (``{"role": "assistant", "tool_calls": [{"function": {"name": ...}}]}``),
    since `Trace.messages` is typed as plain ``list[dict]`` with no single
    mandated shape.
    """
    names: list[str] = []
    for msg in messages:
        tool_calls = msg.get("tool_calls")
        if not tool_calls:
            continue

        if msg.get("type") not in ("ai", "assistant") and msg.get("role") not in (
            "ai",
            "assistant",
        ):
            continue

        for tc in tool_calls:
            name = tc.get("name") or (tc.get("function") or {}).get("name")
            if name:
                names.append(name)
    return names


def _synthetic_messages(tool_names: list[str]) -> list[dict[str, Any]]:
    """One assistant message per tool name, each with exactly one tool call.

    A deliberately reduced representation (see module docstring) so that
    "order" and "count" mean "tool-call order/count", independent of how
    many real messages/turns the calls were spread across.
    """
    return [
        {
            "type": "ai",
            "content": "",
            "tool_calls": [
                {"name": name, "args": {}, "id": f"expected-{i}", "type": "tool_call"}
            ],
        }
        for i, name in enumerate(tool_names)
    ]


def _diagnose(mode: str, actual: list[str], expected: list[str]) -> str:
    """Human-readable reason a trajectory check failed.

    Names the specific tool call(s) missing, unexpected, or out of order —
    a trajectory failure the reader cannot diagnose from a bare pass/fail is
    nearly useless.
    """
    missing = list((Counter(expected) - Counter(actual)).elements())
    extra = list((Counter(actual) - Counter(expected)).elements())
    parts: list[str] = []
    if missing:
        parts.append(f"missing tool call(s): {missing}")

    if mode != "subset" and extra:
        # agentevals' "subset" (our permissive default) never fails on
        # extras — see the naming-gotcha note above — so only surface
        # "unexpected" for strict/unordered, where extras do fail the check.
        parts.append(f"unexpected tool call(s): {extra}")

    if mode == "strict" and not missing and not extra and actual != expected:
        # equal multisets (no missing/extra) imply equal length, so `strict=True`
        # is safe here — it's just documenting that invariant to the linter.
        for i, (act, exp) in enumerate(zip(actual, expected, strict=True)):
            if act != exp:
                parts.append(
                    f"order mismatch at position {i}: expected {exp!r}, got {act!r}"
                )
                break
    if not parts:
        parts.append(f"actual={actual!r} expected={expected!r}")

    return "; ".join(parts) + f" (actual={actual!r} expected={expected!r})"


class TrajectoryMatchMetric:
    """Deterministic tool-call trajectory match, backed by `agentevals`.

    Three registered variants share this implementation:
    - ``"trajectory_match"`` (mode="subset", the default) — every expected
      tool call must have been made; the agent may legitimately call extra
      tools on top of them.
    - ``"trajectory_match_strict"`` (mode="strict") — exact tool-call order
      and count, no extras, no omissions.
    - ``"trajectory_match_unordered"`` (mode="unordered") — the same set of
      tool calls (full multiset equality) in any order.
    """

    def __init__(self, mode: str = "subset") -> None:
        if mode not in _MODE_TO_AGENTEVALS_MODE:
            raise ValueError(f"unknown trajectory mode: {mode!r}")
        self.mode = mode
        self.name = (
            "trajectory_match" if mode == "subset" else f"trajectory_match_{mode}"
        )
        self._evaluator = create_trajectory_match_evaluator(
            trajectory_match_mode=_MODE_TO_AGENTEVALS_MODE[mode],
            tool_args_match_mode="ignore",
        )

    def evaluate(
        self, golden: Golden, trace: Trace, oracle: Oracle | None = None
    ) -> CheckResult:
        if golden.expected_trajectory is None:
            return CheckResult(
                name=self.name,
                passed=True,
                detail="not_applicable: golden has no expected_trajectory",
            )
        expected = golden.expected_trajectory
        actual = _extract_tool_call_names(trace.messages)
        result = self._evaluator(
            outputs=_synthetic_messages(actual),
            reference_outputs=_synthetic_messages(expected),
        )
        passed = bool(result["score"])
        detail = (
            f"matched: actual={actual!r} expected={expected!r}"
            if passed
            else _diagnose(self.mode, actual, expected)
        )

        return CheckResult(name=self.name, passed=passed, detail=detail)


register_metric(TrajectoryMatchMetric(mode="subset"))
register_metric(TrajectoryMatchMetric(mode="strict"))
register_metric(TrajectoryMatchMetric(mode="unordered"))
