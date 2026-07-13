"""travel-pi wiring: JsonDatasetStore + LangGraphRunner + registered metrics +
TAXONOMY -> evalkit.cli.main() (agent-eval-pipeline task 3.1).

The only place that glues `eval/adapters` (the travel-pi binding) to
`evalkit`'s framework-free CLI. ``python -m eval --suite smoke --dry-run``
must work with zero keys/DB/network: dry-run never calls
`agent_runner.run()`, and constructing `LangGraphRunner()` only compiles the
graph — each node resolves its LLM lazily on invocation (see
`app.agents.graph.build_graph`), so no provider key is needed just to list
goldens.
"""

from __future__ import annotations

import logging
import os
import sys

import evalkit.metrics  # noqa: F401 - import side effect: registers deterministic/trajectory/judged/oracle metrics
from app.agents.context import AgentContext
from app.core.config import get_settings
from app.db.engine import get_session_factory
from evalkit import cli
from evalkit.dataset import JsonDatasetStore
from evalkit.metrics.oracle import make_oracle_fact_check_metric
from evalkit.registry import list_metrics, register_metric

from eval.adapters.config import DATASET_DIR, TAXONOMY
from eval.adapters.langgraph_runner import LangGraphRunner

logger = logging.getLogger(__name__)

# Same placeholder set the legacy `eval/run_deepeval.has_real_openai_key` used
# (that module is removed in task 4.1's cleanup) — this repo ships a fake
# `OPENAI_API_KEY=test` in `.env`, which must never be treated as "real".
_PLACEHOLDER_JUDGE_KEYS = {"", "test", "changeme", "placeholder"}


def _judge_available() -> bool:
    """True only when OPENAI_API_KEY is set to a real (non-placeholder) value."""
    return (
        os.environ.get("OPENAI_API_KEY") or ""
    ).strip().lower() not in _PLACEHOLDER_JUDGE_KEYS


# travel-pi has no capability-specific metric-default override today — every
# golden in eval/datasets/*.json declares its own `metrics` explicitly (task
# 2.4) — so this is an empty safety net; a golden that omits `metrics` falls
# through to `evalkit.runner.DEFAULT_METRIC_NAMES`. Add entries here (never
# in evalkit/) if that ever changes.
DEFAULT_METRICS_BY_CAPABILITY: dict[str, list[str]] = {}

try:
    # task 3.2 (landed concurrently): Oracle port impl, recomputes ground
    # truth via the same repositories/services the agent's tools use. `DbOracle`
    # is bound to a single `Session` (never a request-scoped one — this is
    # background/CLI code, per CLAUDE.md), so it can only be constructed inside
    # `main()`, once an isolated session is open.
    from eval.adapters.db_oracle import DbOracle
except ImportError:
    DbOracle = None


def _prod_agent_context(session_factory) -> AgentContext:
    """Load the DB agent config and mirror how a real request builds its context.

    Without this the graph runs on the env-default models (`gpt-5`/`gpt-5-mini`)
    and with reflection forced on — neither is what production serves, so the
    scores would grade an agent nobody ships (agent memory
    `eval-harness-bypasses-db-config-and-context`). `configure` + `reload_from_db`
    mirror `app/core/lifespan.py`; the reflection flag mirrors
    `app/routers/agent.py::_resolve_context`.
    """
    from app.agents.context import resolve_agent_context
    from app.core.agent_config_cache import AgentConfigCache, reload_from_db

    settings = get_settings()
    AgentConfigCache.configure(session_factory, settings.agent_config_cache_ttl_seconds)
    reload_from_db(session_factory)

    refl = AgentConfigCache.get("reflection")
    allow_reflection = True if (refl is None or refl.enabled is None) else refl.enabled
    logger.warning(
        "[EVAL] agent config loaded from DB (allow_reflection=%s)", allow_reflection
    )
    return resolve_agent_context(tier=None, allow_reflection=allow_reflection)


def main() -> int:
    # `evalkit.metrics` (imported above) already registered every metric by
    # this point, so `list_metrics()` is the complete real vocabulary — a
    # golden naming an unregistered metric now fails loudly at load time
    # instead of KeyError-ing mid-run, minutes into a judged full suite.
    dataset_store = JsonDatasetStore(
        DATASET_DIR, TAXONOMY, known_metrics=set(list_metrics())
    )

    # Wire the real extractor into `oracle_fact_check` only when a real judge/
    # LLM key is configured — `llm_extract` (eval/adapters/extractor.py) makes
    # a live LLM call, so without a key it would either fail loudly per golden
    # or (worse) silently degrade every check to "no claimed value found". With
    # no key, the no-op default registered by `evalkit.metrics.oracle` stays
    # in place and reports `not_applicable`, keeping the keyless smoke suite
    # green and honest rather than quietly skipping real checks.
    judge_available = _judge_available()
    if judge_available:
        from eval.adapters.extractor import llm_extract

        register_metric(make_oracle_fact_check_metric(llm_extract))
        logger.warning(
            "[EVAL] oracle_fact_check: wired with llm_extract (judge key present)"
        )
    else:
        logger.warning(
            "[EVAL] oracle_fact_check: no judge key — leaving no-op default "
            "registered (reports not_applicable)"
        )

    # An isolated session (never the request-scoped one) — see engine.py's
    # own lifespan usage of the same `sessionmaker()()` pattern. Constructing
    # it does not open a connection (SQLAlchemy `Session`s connect lazily), so
    # this is still safe for `--dry-run`, which never reaches the oracle.
    session_factory = get_session_factory(get_settings().database_url)

    # `--dry-run` must stay DB-free (module docstring), and it never invokes the
    # agent — so the DB-backed per-agent config is only loaded for a real run.
    dry_run = "--dry-run" in sys.argv[1:]
    agent_runner = LangGraphRunner(
        context=None if dry_run else _prod_agent_context(session_factory)
    )

    with session_factory() as session:
        oracle = DbOracle(session) if DbOracle is not None else None
        return cli.main(
            sys.argv[1:],
            dataset_store=dataset_store,
            agent_runner=agent_runner,
            metrics=DEFAULT_METRICS_BY_CAPABILITY,
            taxonomy=TAXONOMY,
            oracle=oracle,
            judge_available=judge_available,
        )


if __name__ == "__main__":
    sys.exit(main())
