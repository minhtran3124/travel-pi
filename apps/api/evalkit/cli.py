"""Framework-free CLI: ``--suite smoke|full --capability X --language vi|en
--repeat k --out report.json --dry-run`` (agent-eval-pipeline task 3.1).

Every dependency (dataset store, agent runner, metrics, taxonomy, oracle) is
INJECTED by the caller via keyword arguments to `main()` — this module never
imports `app.*`/fastapi/sqlalchemy/langgraph/langchain, keeping it exactly as
portable as the rest of `evalkit/` (`tests/eval/test_boundary.py` enforces
this over this file too). A project wires its own bindings and calls `main()`
from its own entrypoint — see `eval/__main__.py` for the travel-pi wiring.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from typing import Any

from evalkit.ports import AgentRunner, DatasetStore, Oracle
from evalkit.registry import Taxonomy
from evalkit.report import Report, report_exit_code, save_report
from evalkit.runner import resolve_metric_names, run_eval


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="eval", description="Run the capability x scenario agent eval suite."
    )
    parser.add_argument("--suite", required=True, choices=["smoke", "full"])
    parser.add_argument("--capability", default=None)
    parser.add_argument("--language", default=None, choices=["vi", "en"])
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--out", default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def _print_dry_run(
    goldens: Sequence[Any], metrics: Mapping[str, Sequence[str]]
) -> None:
    print(f"[dry-run] {len(goldens)} golden(s) selected — no agent invoked")
    for golden in goldens:
        names = ", ".join(resolve_metric_names(golden, metrics))
        print(
            f"  {golden.id}  {golden.capability}/{golden.scenario}  metrics=[{names}]"
        )


def _print_summary(report: Report) -> None:
    print(f"schema_version={report.schema_version}")
    for capability in sorted(report.per_capability):
        stats = report.per_capability[capability]
        status = "ok" if stats["meets_threshold"] else "BELOW THRESHOLD"
        print(
            f"  {capability:<20} passed={stats['passed']}/{stats['total']}"
            f" pass_rate={stats['pass_rate']:.1%}"
            f" threshold={stats['threshold']:.1%}  {status}"
        )
    skipped = report.run_meta.get("skipped_judged_metrics")
    if skipped:
        print(f"  skipped judged metrics (no judge key configured): {skipped}")


def main(
    argv: Sequence[str] | None = None,
    *,
    dataset_store: DatasetStore,
    agent_runner: AgentRunner,
    metrics: Mapping[str, Sequence[str]],
    taxonomy: Taxonomy,
    oracle: Oracle | None = None,
    judge_available: bool = True,
) -> int:
    """Parse *argv* and run the suite. Returns a process exit code.

    :param argv: CLI args (excluding the program name); ``None`` reads
        `sys.argv[1:]` via argparse's own default.
    :param dataset_store: `DatasetStore` port impl to load goldens from.
    :param agent_runner: `AgentRunner` port impl to drive the agent.
    :param metrics: Per-capability default metric-NAME set, passed straight
        through to `evalkit.runner.run_eval`.
    :param taxonomy: Project taxonomy (capabilities/scenarios/thresholds).
    :param oracle: Optional `Oracle` port impl for fact-checking metrics.
    :param judge_available: Whether a real judge key is configured; when
        False, judged metrics are skipped rather than invoked.
    """
    args = _build_parser().parse_args(argv)

    goldens = dataset_store.load(
        suite=args.suite, capability=args.capability, language=args.language
    )

    if args.dry_run:
        _print_dry_run(goldens, metrics)
        return 0

    report = run_eval(
        goldens,
        agent_runner,
        metrics,
        taxonomy,
        oracle=oracle,
        repeat=args.repeat,
        judge_available=judge_available,
        run_meta={
            "suite": args.suite,
            "capability": args.capability,
            "language": args.language,
        },
    )

    if args.out:
        save_report(report, args.out)
        print(f"report written to {args.out}")

    _print_summary(report)
    return report_exit_code(report)
