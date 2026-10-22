"""OracleFactCheck: DB-as-Oracle deterministic fact-checking metric
(agent-eval-pipeline task 3.2).

Implements the "LLM parses, code computes" split from
`docs/solutions/agent/llm-parses-code-computes.md`: for each
``golden.oracle_checks`` entry, an injected *extractor* pulls the claimed
value out of ``trace.reply`` — parsing only, it never says whether the value
is right — and this module's comparison code decides agreement against
``oracle.lookup()``. Turns "no_hallucination" from a rubric opinion into a
computation for whatever facts a project's `Oracle` can compute.

The extractor is injected (never imported), so this module needs no LLM
client and evalkit stays framework-free — the ast boundary test
(`tests/eval/test_boundary.py`) must stay green. Production wires a real LLM
structured-output call (task 3.1's runner/`eval/__main__.py`); tests use a
hand-written stub, so the whole suite runs offline.

Per `evalkit/ports.py`, `Oracle` is passed to `evaluate()` per-call (not
bound at construction) — a runner can swap oracles, or run with none,
without re-registering the metric.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from evalkit.ports import Oracle
from evalkit.registry import register_metric
from evalkit.types import CheckResult, Golden, Trace


class ExtractionError(RuntimeError):
    """The extractor could not RUN (bad model/key/schema) — an eval-config bug.

    Strictly different from "the reply claimed nothing", which is `None`/`{}`
    and is a verdict about the agent. Collapsing the two is not a style choice:
    a 403 from the extractor's provider once made every `oracle_fact_check`
    report "extractor found no claimed value" and FAIL the case, i.e. the eval
    blamed a correct agent for its own misconfiguration. Raising instead aborts
    the run with a fixable message, and never manufactures a verdict from an
    answer nobody read.
    """


# `extractor(reply, kind, params) -> dict[str, Any] | None`. Returns the
# subset of oracle-shaped fields it could find stated as fact in `reply`
# (e.g. `{"min_price": 123.0}`), or `None`/`{}` when it found no claim at all
# relevant to `kind`. It must raise `ExtractionError` when it cannot run at
# all — never return `None` for that. Production: an LLM structured-output
# call (extraction only — see the module docstring). Tests: a hand-written stub.
Extractor = Callable[[str, str, "dict[str, Any]"], "dict[str, Any] | None"]

# Absolute tolerance for float-valued fields (prices etc.), in the field's own
# unit (USD for every current kind). Counts/codes/flags always compare exact —
# see `_compare_field`.
_DEFAULT_TOLERANCE = 1.0


def _compare_field(
    key: str, expected: Any, claimed: Any, tolerance: float
) -> str | None:
    """Return a human-readable mismatch, or `None` if *claimed* agrees.

    Comparison rule is type-driven, not name-driven: a `float` field (prices,
    rates, ...) gets the numeric *tolerance*; anything else (`int` counts,
    `str` codes, `bool` flags, `None`) must match exactly.
    """
    if expected is None or claimed is None:
        return (
            None
            if expected == claimed
            else f"{key}: oracle={expected!r} claimed={claimed!r}"
        )
    if isinstance(expected, float) or isinstance(claimed, float):
        try:
            if abs(float(claimed) - float(expected)) <= tolerance:
                return None
        except (TypeError, ValueError):
            pass
        return f"{key}: oracle={expected!r} claimed={claimed!r} (tolerance={tolerance})"
    if expected == claimed:
        return None
    return f"{key}: oracle={expected!r} claimed={claimed!r}"


def _compare(
    expected: dict[str, Any], claimed: dict[str, Any], tolerance: float
) -> tuple[bool, dict[str, Any], str]:
    """Compare only the fields *claimed* actually asserts (a subset of *expected*).

    A field name in *claimed* but unknown to *expected* is ignored — the
    extractor may surface something the oracle doesn't model for this kind.
    Returns ``(agrees, overlap, detail)``; an empty *overlap* means nothing
    claimed maps onto a known oracle field (the caller treats this the same
    as "no claim found").
    """
    overlap = {k: v for k, v in claimed.items() if k in expected}
    if not overlap:
        return False, overlap, "no overlapping fields"
    mismatches = [
        m
        for k, v in overlap.items()
        if (m := _compare_field(k, expected[k], v, tolerance)) is not None
    ]
    if mismatches:
        return False, overlap, "; ".join(mismatches)
    return True, overlap, ", ".join(f"{k}={v!r}" for k, v in overlap.items())


class OracleFactCheck:
    """Per `golden.oracle_checks` entry: extract a claim, then let CODE (not
    the extractor) decide agreement against `oracle.lookup()`.

    Convention (matches `evalkit/metrics/deterministic.py`): "not applicable"
    is explicit — a golden with no `oracle_checks`, a run with no `oracle`
    configured, or a metric instance with no `extractor` configured all
    return `passed=True` with a `"not_applicable: "`-prefixed detail, never a
    silent skip that reads as a real pass.
    """

    name = "oracle_fact_check"

    def __init__(
        self, extractor: Extractor | None = None, tolerance: float = _DEFAULT_TOLERANCE
    ) -> None:
        self._extractor = extractor
        self._tolerance = tolerance

    def evaluate(
        self, golden: Golden, trace: Trace, oracle: Oracle | None
    ) -> CheckResult:
        if not golden.oracle_checks:
            return CheckResult(
                name=self.name,
                passed=True,
                detail="not_applicable: golden has no oracle_checks",
            )
        if oracle is None:
            return CheckResult(
                name=self.name,
                passed=True,
                detail="not_applicable: no oracle configured for this run",
            )
        if self._extractor is None:
            return CheckResult(
                name=self.name,
                passed=True,
                detail="not_applicable: no extractor configured for this metric",
            )

        matched: list[str] = []
        skipped: list[str] = []
        for i, check in enumerate(golden.oracle_checks):
            kind = check["kind"]
            params = check.get("params", {})
            tag = f"[{i}] {kind}"

            if not oracle.supports(kind):
                skipped.append(f"{tag}: unsupported by this oracle")
                continue

            try:
                expected = oracle.lookup(kind, params)
            except Exception as exc:  # noqa: BLE001 - surfaced verbatim in detail
                return CheckResult(
                    name=self.name,
                    passed=False,
                    detail=f"{tag}: oracle lookup failed: {exc!r}",
                )

            # An `ExtractionError` here is deliberately NOT caught: the eval
            # itself is broken, so every verdict it would go on to produce is
            # worthless. Let it abort the run (the CLI turns it into a fixable
            # message) rather than silently recording agent failures.
            claimed = self._extractor(trace.reply, kind, params) or {}
            agrees, overlap, detail = _compare(expected, claimed, self._tolerance)

            if not overlap:
                return CheckResult(
                    name=self.name,
                    passed=False,
                    detail=(
                        f"{tag}: extractor found no claimed value for "
                        f"oracle={expected!r} in reply {trace.reply!r}"
                    ),
                )
            if not agrees:
                return CheckResult(
                    name=self.name,
                    passed=False,
                    detail=(
                        f"{tag}: MISMATCH oracle={expected!r} claimed={claimed!r} "
                        f"({detail})"
                    ),
                )
            matched.append(f"{tag}: oracle={expected!r} claimed={claimed!r} OK")

        if not matched:
            # Every check in this golden hit an unsupported kind.
            return CheckResult(
                name=self.name,
                passed=True,
                detail="not_applicable: " + "; ".join(skipped),
            )
        return CheckResult(
            name=self.name, passed=True, detail="; ".join(matched + skipped)
        )


def make_oracle_fact_check_metric(
    extractor: Extractor, tolerance: float = _DEFAULT_TOLERANCE
) -> OracleFactCheck:
    """Factory for a project-configured `oracle_fact_check` metric instance.

    A runner/adapter (e.g. `eval/__main__.py`, task 3.1) supplies the real
    extractor (an LLM structured-output call) and re-registers the result::

        register_metric(make_oracle_fact_check_metric(llm_extract))

    overriding the no-op default registered below — mirrors
    `evalkit/metrics/deterministic.py`'s `make_tool_args_shape_metric`.
    """
    return OracleFactCheck(extractor, tolerance)


# No-op default: registered so `oracle_fact_check` resolves by name even
# before a project wires a real extractor. Any golden declaring
# `oracle_checks` against this default reports `not_applicable` (see
# `evaluate`), never a silent/accidental pass-as-if-checked.
register_metric(OracleFactCheck())
