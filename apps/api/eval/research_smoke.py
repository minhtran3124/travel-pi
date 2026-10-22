"""Keyed smoke for the trip-research deep agent (design §9, task 7.2) — NOT in CI.

Two paths, one seeded trip:

- ``--dry-run`` lists the seeded trip it would research and exits 0 **without** a
  provider key and without ever building or invoking the agent. This is the
  CI-safe path (SC-25); it runs green under ``OPENAI_API_KEY=`` empty.
- default (a real key present) runs exactly one research turn on the seeded trip,
  then asserts the dossier files exist, ``validate_proposal`` reports the proposal
  valid, and the run's recorded cost is at or below ``--max-usd``. A report is
  written to ``eval/reports/research-smoke.json``.

The run can never hang: it is bounded by ``settings.research_timeout_s`` (the same
guard the background runner uses), overridable with ``--timeout``.

Run it as a module from ``apps/api``::

    DATABASE_URL=sqlite:///:memory: OPENAI_API_KEY= \
      ../../.venv/bin/python -m eval.research_smoke --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import get_settings
from app.db.base import Base
from app.db.engine import get_session_factory
from app.repositories.trip import TripRepository
from app.schemas.trip import Trip
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)

# A deterministic owner + trip so a re-run reuses the same dossier thread instead
# of piling up rows. The ids are strings (UUIDBase.id is a String column).
_SMOKE_USER_ID = "research-smoke-user"
_SMOKE_TRIP_ID = "research-smoke-trip"
_RESEARCH_NS_KIND = "research"
_PROPOSAL_KEY = "/proposal.json"
_REPORT_PATH = Path("eval/reports/research-smoke.json")

# Same placeholder set eval/__main__.py treats as "no real key" — this repo ships a
# fake OPENAI_API_KEY=test in .env, which must never be taken for a real key.
_PLACEHOLDER_KEYS = {"", "test", "changeme", "placeholder"}


def _has_real_key() -> bool:
    return (
        os.environ.get("OPENAI_API_KEY") or ""
    ).strip().lower() not in _PLACEHOLDER_KEYS


def _is_memory_sqlite(url: str) -> bool:
    return url.startswith("sqlite") and (":memory:" in url or url == "sqlite://")


def _resolve_factory(url: str) -> sessionmaker[Session]:
    """The session factory the smoke drives the DB through.

    For a persistent URL (Postgres, a sqlite file) this is the process-wide factory
    the agent's own tools resolve via ``session_scope()``, so the trip we seed and
    the ids ``validate_proposal`` checks share one engine. A bare in-memory sqlite
    gives each connection its own empty database, so the dry-run path builds a
    ``StaticPool`` engine instead — one shared connection for create/seed/read.
    """
    if _is_memory_sqlite(url):
        engine = create_engine(
            url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            future=True,
        )
        return sessionmaker(bind=engine, expire_on_commit=False, future=True)
    return get_session_factory(url)


def _ensure_trip(factory: sessionmaker[Session]) -> tuple[str, str]:
    """Create (idempotently) and return the seeded ``(user_id, trip_id)``."""
    repo = TripRepository(factory)
    existing = repo.get_trip(_SMOKE_TRIP_ID, _SMOKE_USER_ID)
    if existing is None:
        repo.create_trip(
            Trip(
                id=_SMOKE_TRIP_ID,
                title="Research smoke — Da Nang long weekend",
                city="Da Nang",
                travelers=2,
                created_at=datetime.now(UTC),
            ),
            _SMOKE_USER_ID,
        )
    return _SMOKE_USER_ID, _SMOKE_TRIP_ID


def _setup_db(factory: sessionmaker[Session], *, seed: bool) -> tuple[str, str]:
    """Create the schema, optionally seed the catalog, and ensure the smoke trip."""
    Base.metadata.create_all(factory().get_bind(), checkfirst=True)
    if seed:
        # A real run researches against real places/flights/hotels; the dry-run
        # only needs the trip to exist, so it skips the (slower) catalog seed.
        from app.db.seed import seed_all

        seed_all(factory)
    return _ensure_trip(factory)


def _research_namespace(user_id: str, trip_id: str) -> tuple[str, ...]:
    return ("users", user_id, _RESEARCH_NS_KIND, trip_id)


def _validate_proposal(store: object, user_id: str, trip_id: str) -> dict:
    """Run the grader's ``validate_proposal`` against the dossier proposal.

    Builds the real tool (``app/research/validate.py``) over a backend that returns
    the stored ``/proposal.json``, so the DB id-resolution logic is exercised
    unchanged rather than re-implemented here.
    """
    from app.research.validate import PROPOSAL_PATH, make_validate_proposal
    from deepagents.backends.protocol import FILE_NOT_FOUND, FileDownloadResponse

    item = store.get(_research_namespace(user_id, trip_id), _PROPOSAL_KEY)
    content = item.value["content"].encode("utf-8") if item is not None else None

    class _ProposalBackend:
        def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
            return [
                FileDownloadResponse(
                    path=paths[0],
                    content=content,
                    error=None if content is not None else FILE_NOT_FOUND,
                )
            ]

    tool = make_validate_proposal(_ProposalBackend())
    _ = PROPOSAL_PATH  # documents the path the tool reads
    return tool.invoke({})


def _write_report(report: dict) -> None:
    _REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True), "utf-8")


def _run_real(args: argparse.Namespace) -> int:
    """One real research turn, then assert files, proposal validity and cost."""
    from app.research.agent import build_research_agent
    from app.research.progress import ProgressBus
    from app.research.runner import run_trip_research
    from app.research.service import ResearchService
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.store.memory import InMemoryStore

    settings = get_settings()
    if args.timeout is not None:
        # The runner reads settings.research_timeout_s for its own asyncio.timeout,
        # so overriding it here bounds the whole turn with the chosen --timeout.
        settings.research_timeout_s = args.timeout

    factory = _resolve_factory(settings.database_url)
    user_id, trip_id = _setup_db(factory, seed=True)

    store = InMemoryStore()
    bus = ProgressBus()
    agent = build_research_agent(store=store, checkpointer=MemorySaver())
    service = ResearchService(
        session_factory=factory, store=store, agent=agent, bus=bus
    )

    run_id = service.start(user_id, trip_id, args.instruction)
    ctx = service._context(run_id, user_id, trip_id)  # noqa: SLF001 — smoke reuse
    asyncio.run(
        run_trip_research(
            run_id=run_id,
            ctx=ctx,
            instruction=args.instruction,
            agent=agent,
            bus=bus,
            session_factory=factory,
        )
    )

    run = service.status(run_id)
    files = sorted(
        item.key for item in store.search(_research_namespace(user_id, trip_id))
    )
    validation = _validate_proposal(store, user_id, trip_id)
    cost = float(run.cost_usd or 0.0) if run is not None else 0.0

    checks = {
        "run_completed": run is not None and run.status == "completed",
        "files_exist": bool(files),
        "proposal_valid": bool(validation.get("valid")),
        "cost_within_budget": cost <= args.max_usd,
    }
    passed = all(checks.values())
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "user_id": user_id,
        "trip_id": trip_id,
        "run_id": run_id,
        "status": run.status if run is not None else "unknown",
        "files": files,
        "proposal_valid": bool(validation.get("valid")),
        "unknown_ids": validation.get("unknown_ids", []),
        "cost_usd": cost,
        "max_usd": args.max_usd,
        "timeout_s": settings.research_timeout_s,
        "checks": checks,
        "passed": passed,
    }
    _write_report(report)

    print(json.dumps(report, indent=2, sort_keys=True))
    if passed:
        print(f"PASS — research smoke: {len(files)} dossier files, cost ${cost:.4f}")
        return 0
    failed = [name for name, ok in checks.items() if not ok]
    print(f"FAIL — research smoke: {', '.join(failed)}", file=sys.stderr)
    return 1


def _run_dry(args: argparse.Namespace) -> int:
    """List the seeded trip that would be researched; no key, no agent, no LLM."""
    settings = get_settings()
    factory = _resolve_factory(settings.database_url)
    user_id, trip_id = _setup_db(factory, seed=False)
    print("research smoke — dry run (no agent invoked)")
    print(f"  database_url : {settings.database_url}")
    print(f"  seeded trip  : trip_id={trip_id} user_id={user_id}")
    print(f"  max_usd      : {args.max_usd}")
    return 0


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m eval.research_smoke",
        description="Keyed smoke for the trip-research deep agent (not in CI).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List the seeded trip and exit 0 without a key or the agent.",
    )
    parser.add_argument(
        "--max-usd",
        type=float,
        default=1.0,
        help="Fail if the run's recorded cost exceeds this (default: 1.0).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=None,
        help="Hard bound on the turn in seconds (default: settings.research_timeout_s).",
    )
    parser.add_argument(
        "--instruction",
        default=None,
        help="Optional research instruction (default: the agent's own).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.WARNING)
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    if args.dry_run:
        return _run_dry(args)
    if not _has_real_key():
        print(
            "research smoke needs a real OPENAI_API_KEY for a live run; "
            "use --dry-run for the keyless path.",
            file=sys.stderr,
        )
        return 2
    return _run_real(args)


if __name__ == "__main__":
    sys.exit(main())
