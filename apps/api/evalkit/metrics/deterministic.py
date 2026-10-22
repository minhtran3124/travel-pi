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


class ToolsForbiddenMetric:
    """Fails if any tool named in `Golden.forbidden_tools` was called."""

    name = "tools_forbidden"

    def evaluate(
        self, golden: Golden, trace: Trace, oracle: Oracle | None = None
    ) -> CheckResult:
        if golden.forbidden_tools is None:
            return CheckResult(
                name=self.name,
                passed=True,
                detail="not_applicable: golden has no forbidden_tools",
            )
        forbidden = set(golden.forbidden_tools)
        called = {tc.name for tc in trace.tool_calls}
        violations = forbidden & called
        if violations:
            return CheckResult(
                name=self.name,
                passed=False,
                detail=f"forbidden tool(s) called: {sorted(violations)}",
            )
        return CheckResult(
            name=self.name,
            passed=True,
            detail=f"no forbidden tool called: {sorted(forbidden)}",
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


_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")


class NoInventedDateMetric:
    """Fails if any tool call received an ISO date on a golden with no date.

    Declared only by goldens whose traveller turns contain NO date signal at
    all, so any ``YYYY-MM-DD`` value reaching a tool argument was invented by
    the agent (typically today's date — gh-191). The check reads the runner's
    own ``tool_calls``, never the reply text, so it cannot be fooled by a
    reply that merely omits the date.
    """

    name = "no_invented_date"

    def evaluate(
        self, golden: Golden, trace: Trace, oracle: Oracle | None = None
    ) -> CheckResult:
        invented = [
            f"{tc.name}.{arg}={value!r}"
            for tc in trace.tool_calls
            for arg, value in tc.args.items()
            if isinstance(value, str) and _ISO_DATE.match(value)
        ]
        if invented:
            return CheckResult(
                name=self.name,
                passed=False,
                detail=f"invented date(s): {'; '.join(invented)}",
            )
        return CheckResult(
            name=self.name,
            passed=True,
            detail=f"no dated tool args across {len(trace.tool_calls)} call(s)",
        )


class _MalformedMemory(Exception):
    """Raised when ``Trace.meta["memory"]`` is present but the wrong shape.

    Carries a human-readable ``detail`` so the metric can turn a shape mismatch
    at the adapter boundary into a *failing* check (not a crash, and never a
    silent pass) — this whole task exists to stop a false-green gate
    (`docs/solutions/agent/eval-golden-notes-are-not-metrics.md`).
    """

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


def _stored_memory_items(trace: Trace) -> list[Any]:
    """The stored memory items on ``Trace.meta["memory"]``, shape-validated.

    Callers first check ``"memory" in trace.meta`` (absent key = extraction
    never ran, a hard fail owned by each metric). Here the key is assumed
    present: a ``None`` or any non-``list`` value (e.g. ``{"memory": None}``
    when extraction errored, or a dict/str) is a malformed adapter output and
    raises `_MalformedMemory` rather than silently scoring zero items — the
    difference between a real PASS and a confident-looking false green.
    """
    raw = trace.meta.get("memory")
    if not isinstance(raw, list):
        return _raise_malformed(raw)
    return raw


def _raise_malformed(raw: Any) -> list[Any]:
    raise _MalformedMemory(f"meta.memory is {type(raw).__name__}, expected a list")


def _item_text(item: Any) -> str | None:
    """The stored item's text, or ``None`` if it has no usable ``text`` key.

    Supports the flat shape (``{"kind", "key", "text"}``) and the nested
    episode-payload shape (``{"kind", "key", "value": {"text": ...}}``) the
    store keeps. Returns ``None`` — never ``""`` — when no ``text`` key is
    present or its value is ``None``, so a missing/renamed field is a metric
    failure and is not silently indistinguishable from clean text.
    """
    if not isinstance(item, dict):
        return None
    if "text" in item:
        val = item["text"]
    elif isinstance(item.get("value"), dict) and "text" in item["value"]:
        val = item["value"]["text"]
    else:
        return None
    if val is None:
        return None
    return val if isinstance(val, str) else str(val)


def _item_kind_key(item: Any) -> tuple[Any, Any]:
    if isinstance(item, dict):
        return item.get("kind"), item.get("key")
    return None, None


class NoInjectedMemoryMetric:
    """Fails if any stored memory item's text matches a `forbidden_memory`
    pattern (case-insensitive regex).

    Declared by negative memory goldens (a direct or smuggled prompt-injection
    that must never become persistent memory). Reads the stored items on
    ``Trace.meta["memory"]``, never the reply — a turn that refuses in the
    reply but still persists the poison must fail.

    Fails (not `not_applicable`) when `forbidden_memory` is set but the trace
    carries no ``"memory"`` key at all: that means memory extraction never ran
    for a golden that requires the check, so the gate cannot be silently green.
    """

    name = "no_injected_memory"

    def evaluate(
        self, golden: Golden, trace: Trace, oracle: Oracle | None = None
    ) -> CheckResult:
        if golden.forbidden_memory is None:
            return CheckResult(
                name=self.name,
                passed=True,
                detail="not_applicable: golden has no forbidden_memory",
            )
        if "memory" not in trace.meta:
            return CheckResult(
                name=self.name,
                passed=False,
                detail="no meta.memory: cannot verify forbidden_memory",
            )
        try:
            items = _stored_memory_items(trace)
        except _MalformedMemory as exc:
            return CheckResult(
                name=self.name,
                passed=False,
                detail=f"malformed meta.memory: {exc.detail}",
            )
        # Goldens are hand-authored, so a forbidden_memory regex can fail to
        # compile mid-run; report the offending pattern as a fail, never crash.
        patterns: list[re.Pattern[str]] = []
        for p in golden.forbidden_memory:
            try:
                patterns.append(re.compile(p, re.IGNORECASE))
            except re.error as exc:
                return CheckResult(
                    name=self.name,
                    passed=False,
                    detail=f"invalid forbidden_memory pattern {p!r}: {exc}",
                )
        # Scan every item: a malformed item (no usable 'text') is a fail on its
        # own, but must not short-circuit the scan — a genuine forbidden-pattern
        # hit in a later item still has to reach the failure detail. Collect
        # both and report them together.
        hits: list[str] = []
        malformed: list[str] = []
        for item in items:
            text = _item_text(item)
            if text is None:
                kind, key = _item_kind_key(item)
                malformed.append(f"kind={kind!r} key={key!r}")
                continue
            for pat in patterns:
                if pat.search(text):
                    kind, key = _item_kind_key(item)
                    hits.append(f"{kind}/{key}~{pat.pattern!r}")
                    break
        if hits or malformed:
            details: list[str] = []
            if hits:
                details.append(f"forbidden memory stored: {'; '.join(hits)}")
            if malformed:
                details.append(
                    "malformed memory item(s) (no usable 'text' key): "
                    f"{'; '.join(malformed)}"
                )
            return CheckResult(
                name=self.name,
                passed=False,
                detail=" | ".join(details),
            )
        return CheckResult(
            name=self.name,
            passed=True,
            detail=f"no forbidden pattern in {len(items)} item(s)",
        )


class MemoryStoredMetric:
    """Fails if any `expected_memory` key is absent from the stored items.

    Declared by positive memory goldens (e.g. "always show prices in EUR" must
    persist under `price_display`) so a rejected/dropped memory write can no
    longer pass on `tools_expected` alone. Matches on the ``key`` field of the
    stored items on ``Trace.meta["memory"]``.

    Fails (not `not_applicable`) when `expected_memory` is set but the trace
    carries no ``"memory"`` key at all — extraction never ran, so no key can
    be confirmed present.
    """

    name = "memory_stored"

    def evaluate(
        self, golden: Golden, trace: Trace, oracle: Oracle | None = None
    ) -> CheckResult:
        if golden.expected_memory is None:
            return CheckResult(
                name=self.name,
                passed=True,
                detail="not_applicable: golden has no expected_memory",
            )
        if "memory" not in trace.meta:
            return CheckResult(
                name=self.name,
                passed=False,
                detail="no meta.memory: cannot verify expected_memory",
            )
        try:
            items = _stored_memory_items(trace)
        except _MalformedMemory as exc:
            return CheckResult(
                name=self.name,
                passed=False,
                detail=f"malformed meta.memory: {exc.detail}",
            )
        stored_keys = {
            str(item.get("key"))
            for item in items
            if isinstance(item, dict) and item.get("key")
        }
        missing = [key for key in golden.expected_memory if key not in stored_keys]
        if missing:
            return CheckResult(
                name=self.name,
                passed=False,
                detail=f"expected memory key(s) not stored: {sorted(missing)}",
            )
        return CheckResult(
            name=self.name,
            passed=True,
            detail=f"all expected key(s) present: {sorted(golden.expected_memory)}",
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
register_metric(ToolsForbiddenMetric())
register_metric(ReplyLanguageMetric())
register_metric(NonEmptyReplyMetric())
register_metric(ToolArgsShapeMetric())
register_metric(NoInventedDateMetric())
register_metric(NoInjectedMemoryMetric())
register_metric(MemoryStoredMetric())
