"""Judge-free, deterministic eval metrics (agent-eval-pipeline task 1.2).

Pure functions over ``(Golden, Trace)`` — no network, no LLM. Each metric is
a small class instance registered under `.name` via `register_metric` so a
runner can look it up by string (from `Golden.metrics` or a capability
default).

Convention — "not applicable" is explicit, never a silent pass: when a
golden doesn't configure the expectation a metric checks (e.g. no
``expected_flow``), the metric still returns ``passed=True`` (an unconfigured
check can't fail), but `CheckResult.detail` is prefixed ``"not_applicable: "``
so a report reader can tell "this passed because it wasn't checked" apart
from "this passed because it was checked and matched". A metric that
silently no-ops on missing config is a trap — this makes it visible instead.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from evalkit.ports import Oracle
from evalkit.registry import register_metric
from evalkit.types import CheckResult, Golden, Trace


class FlowMatchMetric:
    """Checks `Trace.flow` against `Golden.expected_flow`."""

    name = "flow_match"

    def evaluate(
        self, golden: Golden, trace: Trace, oracle: Oracle | None = None
    ) -> CheckResult:
        if golden.expected_flow is None:
            return CheckResult(
                name=self.name,
                passed=True,
                detail="not_applicable: golden has no expected_flow",
            )
        passed = trace.flow == golden.expected_flow
        return CheckResult(
            name=self.name,
            passed=passed,
            detail=f"expected={golden.expected_flow!r} got={trace.flow!r}",
        )


class ToolsExpectedMetric:
    """Compares the set of tools actually called against `expected_tools`.

    Two registered variants share this implementation:
    - ``"tools_expected"`` (mode="subset", the default) — passes as long as
      every expected tool was called; the agent may legitimately call extra
      tools on top of the expected ones.
    - ``"tools_expected_exact"`` (mode="exact") — the called-tool set must
      equal the expected set exactly.
    """

    def __init__(self, mode: str = "subset") -> None:
        if mode not in ("subset", "exact"):
            raise ValueError(f"unknown tools_expected mode: {mode!r}")
        self.mode = mode
        self.name = "tools_expected" if mode == "subset" else "tools_expected_exact"

    def evaluate(
        self, golden: Golden, trace: Trace, oracle: Oracle | None = None
    ) -> CheckResult:
        if golden.expected_tools is None:
            return CheckResult(
                name=self.name,
                passed=True,
                detail="not_applicable: golden has no expected_tools",
            )
        expected = set(golden.expected_tools)
        called = {tc.name for tc in trace.tool_calls}
        passed = called == expected if self.mode == "exact" else expected <= called
        return CheckResult(
            name=self.name,
            passed=passed,
            detail=f"expected={sorted(expected)} called={sorted(called)}",
        )


class TasksExpectedMetric:
    """Compares the set of sub-agents the supervisor fanned out to against
    `Golden.expected_tasks`, using `Trace.meta["tasks"]` as the source of
    what actually ran.
    """

    name = "tasks_expected"

    def evaluate(
        self, golden: Golden, trace: Trace, oracle: Oracle | None = None
    ) -> CheckResult:
        if golden.expected_tasks is None:
            return CheckResult(
                name=self.name,
                passed=True,
                detail="not_applicable: golden has no expected_tasks",
            )
        expected = set(golden.expected_tasks)
        if "tasks" not in trace.meta:
            return CheckResult(
                name=self.name,
                passed=False,
                detail=f"no meta.tasks: expected={sorted(expected)}",
            )
        got = set(trace.meta["tasks"])
        passed = got == expected
        return CheckResult(
            name=self.name,
            passed=passed,
            detail=f"expected={sorted(expected)} got={sorted(got)}",
        )


def _has_vietnamese_diacritics(text: str) -> bool:
    """True if *text* carries a Vietnamese tone/diacritic mark or 'đ'/'Đ'.

    Detects via NFD decomposition: Unicode combining marks catch the tone
    marks on a/e/i/o/u/y, plus 'đ'/'Đ' checked explicitly since it has no
    NFD decomposition. Same general technique as `app/core/text.py`'s
    `fold_diacritics`, reimplemented here (not imported — evalkit must stay
    free of `app.*` imports, per the portability boundary test).
    """
    if "đ" in text or "Đ" in text:
        return True
    decomposed = unicodedata.normalize("NFD", text)
    return any(unicodedata.combining(ch) for ch in decomposed)


# Small closed-class word lists used only as a fallback when the reply has
# no diacritics at all (i.e. it might be un-accented Vietnamese, or English).
_VI_ASCII_WORDS = {
    "la",
    "va",
    "duoc",
    "khong",
    "cua",
    "toi",
    "ban",
    "minh",
    "nay",
    "cho",
    "mot",
    "co",
}
_EN_WORDS = {
    "the",
    "is",
    "and",
    "you",
    "your",
    "for",
    "this",
    "with",
    "have",
    "are",
    "of",
    "to",
    "in",
    "a",
    "it",
}


def _detect_language(text: str) -> str:
    """Heuristic vi/en detector, self-contained (no `app.core.text` import).

    1. Diacritic check — any Vietnamese tone mark or 'đ' is a strong "vi"
       signal, since this agent writes Vietnamese replies with full tone
       marks.
    2. Function-word fallback — when no diacritic is found, count known
       (unaccented) VI vs EN closed-class words among lowercased tokens.

    Known limits: this is NOT a general-purpose language identifier — it
    only distinguishes vi/en (the two languages the goldens use); it treats
    any Latin-diacritic text (French, Spanish, ...) as "vi"; it assumes
    accented Vietnamese keeps its tone marks (un-accented VI without any of
    the fallback words reads as "en"); and very short or word-list-empty
    replies (numbers, code, a bare name) default to "en" with no signal
    either way.
    """
    if _has_vietnamese_diacritics(text):
        return "vi"
    tokens = re.findall(r"[a-z]+", text.lower())
    vi_hits = sum(1 for t in tokens if t in _VI_ASCII_WORDS)
    en_hits = sum(1 for t in tokens if t in _EN_WORDS)
    return "vi" if vi_hits > en_hits else "en"


class ReplyLanguageMetric:
    """Checks the detected language of `Trace.reply` against `Golden.language`."""

    name = "reply_language"

    def evaluate(
        self, golden: Golden, trace: Trace, oracle: Oracle | None = None
    ) -> CheckResult:
        if not (trace.reply or "").strip():
            # Nothing to detect — e.g. a booking golden stops at the HITL
            # plan-approval interrupt with no reply. `non_empty_reply` is the
            # metric that reports that; a language verdict on "" is noise.
            return CheckResult(
                name=self.name,
                passed=True,
                detail="not_applicable: empty reply — no language to detect",
            )
        detected = _detect_language(trace.reply)
        passed = detected == golden.language
        return CheckResult(
            name=self.name,
            passed=passed,
            detail=f"expected={golden.language!r} detected={detected!r}",
        )


# Bare markers a reply sometimes ends up as when a tool/LLM call fails
# upstream and the failure leaks into the reply text instead of being
# handled — these don't count as a real answer even though non-empty.
_ERROR_MARKERS = {"error", "[error]", "none", "null", "n/a", "undefined"}


class NonEmptyReplyMetric:
    """Checks that `Trace.reply` is non-empty and not a bare error marker."""

    name = "non_empty_reply"

    def evaluate(
        self, golden: Golden, trace: Trace, oracle: Oracle | None = None
    ) -> CheckResult:
        reply = (trace.reply or "").strip()
        if not reply:
            return CheckResult(name=self.name, passed=False, detail="reply is empty")
        if reply.lower() in _ERROR_MARKERS:
            return CheckResult(
                name=self.name,
                passed=False,
                detail=f"reply is a bare error marker: {reply!r}",
            )
        return CheckResult(name=self.name, passed=True, detail=None)


_JSON_SCHEMA_TYPES: dict[str, type | tuple[type, ...]] = {
    "string": str,
    "number": (int, float),
    "integer": int,
    "boolean": bool,
    "array": list,
    "object": dict,
}


def _shape_violations(args: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    """Human-readable violations of *schema* against *args*.

    Supports a minimal JSON-Schema-like subset: top-level ``required`` (list
    of key names) and ``properties`` (name -> ``{"type": <json type name>}``).
    Anything outside this subset is ignored — this is a shape check, not a
    full JSON Schema validator (no new dependency was added for it).
    """
    violations: list[str] = []
    for key in schema.get("required", []):
        if key not in args:
            violations.append(f"missing required arg {key!r}")
    for prop_name, prop in schema.get("properties", {}).items():
        if prop_name not in args:
            continue
        expected_type = prop.get("type")
        py_type = _JSON_SCHEMA_TYPES.get(expected_type)
        if py_type is not None and not isinstance(args[prop_name], py_type):
            got = type(args[prop_name]).__name__
            violations.append(
                f"arg {prop_name!r} expected type {expected_type!r}, got {got}"
            )
    return violations


class ToolArgsShapeMetric:
    """Validates each `ToolCall.args` against a JSON-schema-ish spec per tool.

    `Golden` has no field to carry a per-tool arg schema (and this task must
    not edit `evalkit/types.py`, owned by task 1.1 this wave), so the schema
    map is supplied to the constructor instead: a project adapter (e.g.
    `eval/adapters/config.py`, task 2.1/3.1) builds one via
    `make_tool_args_shape_metric(schemas)` with its own tool-name -> schema
    map and re-registers it under this same name, overriding the no-op
    default registered below. If a future need arises for a *per-golden*
    schema override (not just per-tool-name project-wide), that would need
    a new `Golden` field — flagged as a follow-up, not done here.
    """

    name = "tool_args_shape"

    def __init__(self, schemas: dict[str, dict[str, Any]] | None = None) -> None:
        self.schemas = schemas or {}

    def evaluate(
        self, golden: Golden, trace: Trace, oracle: Oracle | None = None
    ) -> CheckResult:
        if not self.schemas:
            return CheckResult(
                name=self.name,
                passed=True,
                detail="not_applicable: no tool arg schemas configured",
            )
        violations: list[str] = []
        checked = 0
        for tc in trace.tool_calls:
            schema = self.schemas.get(tc.name)
            if schema is None:
                continue
            checked += 1
            violations.extend(
                f"{tc.name}: {v}" for v in _shape_violations(tc.args, schema)
            )
        if checked == 0:
            return CheckResult(
                name=self.name,
                passed=True,
                detail="not_applicable: no tool call matched a configured schema",
            )
        if violations:
            return CheckResult(
                name=self.name, passed=False, detail="; ".join(violations)
            )
        return CheckResult(
            name=self.name, passed=True, detail=f"{checked} tool call(s) matched schema"
        )


def make_tool_args_shape_metric(
    schemas: dict[str, dict[str, Any]],
) -> ToolArgsShapeMetric:
    """Factory for a project-configured `tool_args_shape` metric instance.

    Callers register the result themselves, e.g.::

        register_metric(make_tool_args_shape_metric({"search_flights": {...}}))
    """
    return ToolArgsShapeMetric(schemas)


register_metric(FlowMatchMetric())
register_metric(TasksExpectedMetric())
register_metric(ToolsExpectedMetric(mode="subset"))
register_metric(ToolsExpectedMetric(mode="exact"))
register_metric(ReplyLanguageMetric())
register_metric(NonEmptyReplyMetric())
register_metric(ToolArgsShapeMetric())
