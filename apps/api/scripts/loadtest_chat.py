"""Concurrent-chat load test for the agent (gh-293, specs/prod-deploy-render-concurrency).

Drives N simultaneous ``POST /agent/chat`` turns through the real FastAPI app
(in-process ASGI, so a single process: it measures one web worker, not the
whole 4-process fleet) and records p95 latency, Postgres connection count,
429 count and error rate. With the default ``--llm fake`` every model call is a
deterministic echo, so the run is keyless and free; ``--llm real`` uses the
configured provider (paid, short runs only).

Acceptance (the gate for the 10-chat run): 0 5xx, peak connections under 70% of
``max_connections``, and no state cross-talk. Cross-talk check: each chat sends
a unique token and the fake model echoes the last human message, so a thread's
persisted history may contain only its own token.

    python scripts/loadtest_chat.py --concurrency 5 10 20
    python scripts/loadtest_chat.py --concurrency 10 --database-url postgresql+psycopg://...

Run from ``apps/api/``. Connection counts are only measured on Postgres.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import logging
import os
import statistics
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Settings are read at import time: --database-url must land in the env first.
for _i, _arg in enumerate(sys.argv):
    if _arg == "--database-url" and _i + 1 < len(sys.argv):
        os.environ["DATABASE_URL"] = sys.argv[_i + 1]

import httpx  # noqa: E402
from app.agents.graph import build_graph  # noqa: E402
from app.agents.supervisor import SupervisorIntent  # noqa: E402
from app.clients.llm import FakeLLM  # noqa: E402
from app.core.auth import AuthUser, get_current_user  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.engine import get_engine, get_session_factory  # noqa: E402
from app.db.session import get_session  # noqa: E402
from app.main import create_app  # noqa: E402
from app.routers.agent import get_travel_graph, get_travel_graph_optional  # noqa: E402
from fastapi import Header  # noqa: E402
from langchain_core.messages import AIMessage, HumanMessage  # noqa: E402
from langchain_core.outputs import ChatGeneration, ChatResult  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

CONN_LIMIT_FRACTION = 0.70


class EchoLLM(FakeLLM):
    """FakeLLM that answers ``ack:<last human message>`` so history ownership is checkable."""

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):  # type: ignore[override]
        humans = [m for m in messages if isinstance(m, HumanMessage)]
        last = str(humans[-1].content) if humans else ""
        msg = AIMessage(
            content=f"ack:{last}",
            usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
        )
        return ChatResult(generations=[ChatGeneration(message=msg)])


@dataclass
class Result:
    concurrency: int
    turns_per_chat: int
    processes: int = 1
    requests: int = 0
    ok: int = 0
    status_5xx: int = 0
    status_429: int = 0
    status_other: int = 0
    exceptions: int = 0
    error_rate: float = 0.0
    p50_s: float = 0.0
    p95_s: float = 0.0
    max_s: float = 0.0
    wall_s: float = 0.0
    peak_connections: int | None = None
    max_connections: int | None = None
    crosstalk_violations: int = 0
    passed: bool = False
    notes: list[str] = field(default_factory=list)
    latencies: list[float] = field(default_factory=list, repr=False)


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))]


def _build_fake_graph(checkpointer, store):
    echo = EchoLLM(
        structured_responses=[SupervisorIntent(target_agent="concierge")],
        responses=["ok"],
    )
    return build_graph(
        llm=echo,
        fast_llm=EchoLLM(responses=["ok"]),
        checkpointer=checkpointer,
        store=store,
    )


async def _sample_connections(url: str, stop: asyncio.Event, out: dict) -> None:
    """Peak ``pg_stat_activity`` rows for this database, sampled on its own connection."""
    engine = create_engine(url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            out["max_connections"] = int(
                conn.execute(text("SHOW max_connections")).scalar_one()
            )
            while not stop.is_set():
                n = conn.execute(
                    text(
                        "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()"
                    )
                ).scalar_one()
                # Minus the sampler's own connection.
                out["peak"] = max(out.get("peak", 0), int(n) - 1)
                conn.rollback()
                await asyncio.sleep(0.05)
    finally:
        engine.dispose()


async def _one_chat(
    client: httpx.AsyncClient,
    idx: int,
    run_id: str,
    turns: int,
    res: Result,
    lat: list[float],
):
    user = f"load_{run_id}_{idx}"
    conv = str(uuid.uuid4())
    tokens = []
    for t in range(turns):
        token = f"tok{run_id}x{idx}x{t}"
        tokens.append(token)
        start = time.monotonic()
        try:
            r = await client.post(
                "/agent/chat",
                json={"message": token, "conversation_id": conv},
                headers={"X-Load-User": user},
            )
        except Exception as exc:  # noqa: BLE001 - counted, not fatal
            res.exceptions += 1
            res.notes.append(f"chat {idx} turn {t}: {type(exc).__name__}: {exc}")
            return user, conv, tokens
        lat.append(time.monotonic() - start)
        res.requests += 1
        if r.status_code == 200:
            res.ok += 1
        elif r.status_code == 429:
            res.status_429 += 1
        elif r.status_code >= 500:
            res.status_5xx += 1
            res.notes.append(f"chat {idx} turn {t}: {r.status_code} {r.text[:200]}")
        else:
            res.status_other += 1
            res.notes.append(f"chat {idx} turn {t}: {r.status_code} {r.text[:200]}")
    return user, conv, tokens


async def _verify_history(
    client, user: str, conv: str, tokens: list[str], run_id: str
) -> int:
    """Count foreign tokens in this thread's history (own tokens are fine)."""
    r = await client.get(
        f"/agent/conversations/{conv}/messages", headers={"X-Load-User": user}
    )
    if r.status_code != 200:
        return 1
    violations = 0
    marker = f"tok{run_id}x"
    seen: set[str] = set()
    for m in r.json()["messages"]:
        content = m.get("content") or ""
        # Every token-shaped substring must be one of this chat's own tokens.
        for part in content.replace("ack:", " ").split():
            if part.startswith(marker):
                seen.add(part)
                if part not in tokens:
                    violations += 1
    # A chat whose own turns are missing from its history is also a state fault.
    violations += len(set(tokens) - seen)
    return violations


def _finish(res: Result, lat: list[float]) -> Result:
    """Derive latency stats, error rate and the pass verdict from the raw counters."""
    res.latencies = lat
    res.error_rate = (res.status_5xx + res.exceptions + res.status_other) / max(
        1, res.requests + res.exceptions
    )
    if lat:
        res.p50_s, res.p95_s, res.max_s = statistics.median(lat), _p95(lat), max(lat)
    conn_ok = (
        True
        if res.peak_connections is None
        else res.peak_connections < CONN_LIMIT_FRACTION * (res.max_connections or 0)
    )
    res.passed = (
        res.status_5xx == 0
        and res.exceptions == 0
        and res.crosstalk_violations == 0
        and conn_ok
    )
    return res


async def run_level(
    app, concurrency: int, turns: int, sample_url: str | None, start_at: float = 0.0
) -> Result:
    """One process: ``concurrency`` simultaneous chats; samples connections when ``sample_url`` is set."""
    res = Result(concurrency=concurrency, turns_per_chat=turns)
    run_id = uuid.uuid4().hex[:6]
    lat: list[float] = []
    conn_out: dict = {}
    stop = asyncio.Event()
    sampler = (
        asyncio.create_task(_sample_connections(sample_url, stop, conn_out))
        if sample_url
        else None
    )

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://load", timeout=180
    ) as client:
        if start_at:
            await asyncio.sleep(max(0.0, start_at - time.time()))
        start = time.monotonic()
        chats = await asyncio.gather(
            *[_one_chat(client, i, run_id, turns, res, lat) for i in range(concurrency)]
        )
        res.wall_s = time.monotonic() - start
        checks = await asyncio.gather(
            *[_verify_history(client, u, c, t, run_id) for u, c, t in chats]
        )
    res.crosstalk_violations = sum(checks)

    if sampler:
        stop.set()
        await sampler
        res.peak_connections = conn_out.get("peak")
        res.max_connections = conn_out.get("max_connections")
    return _finish(res, lat)


async def run_level_multiprocess(
    args, url: str, concurrency: int, processes: int
) -> Result:
    """Split ``concurrency`` over ``processes`` child processes (own engine/pool/graph each), mirroring the gunicorn fleet; connections are sampled once, globally."""
    shares = [
        concurrency // processes + (i < concurrency % processes)
        for i in range(processes)
    ]
    shares = [n for n in shares if n]
    # Children build their app first, then all fire at the same wall-clock instant.
    start_at = time.time() + 12
    conn_out: dict = {}
    stop = asyncio.Event()
    sampler = asyncio.create_task(_sample_connections(url, stop, conn_out))
    procs = [
        await asyncio.create_subprocess_exec(
            sys.executable,
            os.path.abspath(__file__),
            "--child",
            "--concurrency",
            str(n),
            "--turns",
            str(args.turns),
            "--llm",
            args.llm,
            "--start-at",
            str(start_at),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=os.environ.copy(),
        )
        for n in shares
    ]
    outs = await asyncio.gather(*[p.communicate() for p in procs])
    stop.set()
    await sampler

    res = Result(
        concurrency=concurrency, turns_per_chat=args.turns, processes=len(shares)
    )
    lat: list[float] = []
    for (out, err), proc in zip(outs, procs, strict=True):
        line = next(
            (ln for ln in out.decode().splitlines() if ln.startswith("RESULT ")), None
        )
        if proc.returncode != 0 or line is None:
            res.exceptions += 1
            res.notes.append(
                f"child failed rc={proc.returncode}: {err.decode()[-300:]}"
            )
            continue
        child = json.loads(line[len("RESULT ") :])
        for k in (
            "requests",
            "ok",
            "status_5xx",
            "status_429",
            "status_other",
            "exceptions",
            "crosstalk_violations",
        ):
            setattr(res, k, getattr(res, k) + child[k])
        res.wall_s = max(res.wall_s, child["wall_s"])
        res.notes.extend(child["notes"])
        lat.extend(child["latencies"])
    res.peak_connections = conn_out.get("peak")
    res.max_connections = conn_out.get("max_connections")
    return _finish(res, lat)


@contextlib.asynccontextmanager
async def _fake_app(url: str):
    from app.agents.checkpointer import open_checkpointer
    from app.memory.store import open_store

    Base.metadata.create_all(get_engine(url), checkfirst=True)
    app = create_app()

    async def _user(x_load_user: str = Header(default="load_anon")):
        return AuthUser(id=x_load_user, email=None, role=None, claims={})

    def _session():
        # Bound to ``url`` explicitly so the app and the sampler always target one database.
        s = get_session_factory(url)()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_current_user] = _user
    async with open_checkpointer(url) as saver, open_store(url) as store:
        graph = _build_fake_graph(saver, store)
        app.dependency_overrides[get_travel_graph] = lambda: graph
        app.dependency_overrides[get_travel_graph_optional] = lambda: graph
        yield app


@contextlib.asynccontextmanager
async def _real_app(url: str):
    """Full app lifespan: the configured provider and graph, with a header-selected user."""
    app = create_app()

    async def _user(x_load_user: str = Header(default="load_anon")):
        return AuthUser(id=x_load_user, email=None, role=None, claims={})

    app.dependency_overrides[get_current_user] = _user
    async with app.router.lifespan_context(app):
        yield app


async def main_async(args) -> int:
    url = get_settings().database_url
    is_pg = url.startswith("postgres")
    results: list[Result] = []

    if args.child:
        factory = _fake_app if args.llm == "fake" else _real_app
        async with factory(url) as app:
            res = await run_level(
                app, args.concurrency[0], args.turns, None, args.start_at
            )
        print("RESULT " + json.dumps(asdict(res)), flush=True)
        return 0

    if args.processes > 1:
        if not is_pg:
            print("--processes > 1 needs Postgres (SQLite cannot be shared).")
            return 2
        for level in args.concurrency:
            results.append(
                await run_level_multiprocess(args, url, level, args.processes)
            )
    else:
        factory = _fake_app if args.llm == "fake" else _real_app
        async with factory(url) as app:
            for level in args.concurrency:
                results.append(
                    await run_level(app, level, args.turns, url if is_pg else None)
                )
    for r in results:
        if not is_pg:
            r.notes.append("SQLite: connection counts not measured")
        print(
            json.dumps({**asdict(r), "latencies": len(r.latencies)}, indent=2),
            flush=True,
        )

    print(
        "\nconcurrency  procs  reqs  5xx  429  p95_s   peak_conn/max  crosstalk  pass"
    )
    for r in results:
        conn = (
            "n/a"
            if r.peak_connections is None
            else f"{r.peak_connections}/{r.max_connections}"
        )
        print(
            f"{r.concurrency:>11}  {r.processes:>5}  {r.requests:>4}  {r.status_5xx:>3}  "
            f"{r.status_429:>3}  {r.p95_s:>5.2f}   {conn:>13}  {r.crosstalk_violations:>9}  {r.passed}"
        )
    # 20 is a headroom check, not a gate: only the <=10 levels decide the exit code.
    gated = [r for r in results if r.concurrency <= 10] or results
    return 0 if all(r.passed for r in gated) else 1


def main() -> int:
    logging.disable(logging.CRITICAL)
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--concurrency", type=int, nargs="+", default=[5, 10, 20])
    p.add_argument("--turns", type=int, default=2, help="sequential turns per chat")
    p.add_argument("--llm", choices=["fake", "real"], default="fake")
    p.add_argument(
        "--database-url", help="override DATABASE_URL (Postgres to measure connections)"
    )
    p.add_argument(
        "--processes",
        type=int,
        default=1,
        help="split each level over this many OS processes (prod: 2 instances x 2 workers = 4)",
    )
    p.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--start-at", type=float, default=0.0, help=argparse.SUPPRESS)
    args = p.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
