"""Checks the local production-topology stack (docker-compose.prodsim.yml); exits 1 on any failure.

Runs as the compose ``verify`` service. Infrastructure only: no chat turn is sent, so no LLM key
and no spend. Every check prints PASS or FAIL with the observed value.
"""

from __future__ import annotations

import concurrent.futures as cf
import os
import sys
import threading
import time
import urllib.error
import urllib.request

import psycopg
import redis

LB = os.environ.get("LB_URL", "http://lb")
INSTANCES = ["http://api-1:8000", "http://api-2:8000"]
DB_DSN = os.environ["DATABASE_URL"].replace("+psycopg", "")
REDIS_URL = os.environ["REDIS_URL"]
BURST_REQUESTS, BURST_THREADS = 300, 60
CONNECTION_CAP = 0.7  # docs/render-deploy.md: stay under 70% of max_connections

results: list[tuple[bool, str, str]] = []


def check(ok: bool, name: str, detail: str = "") -> None:
    results.append((ok, name, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}", flush=True)


def get(url: str, method: str = "GET") -> tuple[int, str, dict]:
    req = urllib.request.Request(url, method=method, data=b"{}" if method == "POST" else None)
    if method == "POST":
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read().decode(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(), dict(e.headers)


def wait_ready(url: str, seconds: int = 60) -> bool:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        try:
            if get(url + "/readyz")[0] == 200:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def pg_connections(cur) -> int:
    cur.execute("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()")
    return cur.fetchone()[0]


def main() -> int:
    # 1. Each web instance is up and ready on its own.
    for base in INSTANCES:
        check(wait_ready(base), f"{base} /readyz is 200")

    # 2. The proxy reaches both instances (round robin), like Render's load balancer.
    seen = set()
    for _ in range(40):
        _, _, headers = get(LB + "/healthz")
        seen.add(headers.get("X-Upstream", "?"))
    check(len(seen) == 2, "proxy balances across both instances", f"upstreams={sorted(seen)}")

    # 3. Production mode: interactive docs are off, protected routes reject anonymous calls.
    check(get(LB + "/docs")[0] == 404, "/docs is disabled in production")
    code = get(LB + "/agent/chat", "POST")[0]
    check(code in (401, 403), "POST /agent/chat without a token is rejected", f"status={code}")

    # 4. Database: migrated once to head, pgvector present, connection cap as configured.
    with psycopg.connect(DB_DSN, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("SELECT version_num FROM alembic_version")
        rows = cur.fetchall()
        check(len(rows) == 1, "alembic_version has exactly one head", f"{rows}")
        cur.execute("SELECT count(*) FROM pg_extension WHERE extname = 'vector'")
        check(cur.fetchone()[0] == 1, "pgvector extension is installed")
        cur.execute("SHOW max_connections")
        max_conn = int(cur.fetchone()[0])
        check(max_conn == 100, "max_connections mirrors the plan", f"max_connections={max_conn}")

        # 5. Burst through the proxy (DB-backed /readyz) and sample connections while it runs.
        peak, stop = [0], threading.Event()

        def sampler() -> None:
            with psycopg.connect(DB_DSN, autocommit=True) as c2, c2.cursor() as cur2:
                while not stop.is_set():
                    peak[0] = max(peak[0], pg_connections(cur2))
                    time.sleep(0.1)

        t = threading.Thread(target=sampler)
        t.start()
        started = time.monotonic()
        with cf.ThreadPoolExecutor(BURST_THREADS) as pool:
            codes = list(pool.map(lambda _: get(LB + "/readyz")[0], range(BURST_REQUESTS)))
        elapsed = time.monotonic() - started
        stop.set()
        t.join()
        bad = [c for c in codes if c != 200]
        check(not bad, f"{BURST_REQUESTS} concurrent /readyz all 200", f"non-200={len(bad)} in {elapsed:.1f}s")
        check(peak[0] <= CONNECTION_CAP * max_conn, "peak Postgres connections under 70% of max",
              f"peak={peak[0]}/{max_conn}")

    # 6. Redis: queue store is safe (noeviction) and the Arq worker is alive.
    r = redis.Redis.from_url(REDIS_URL)
    check(r.ping(), "redis answers PING")
    policy = r.config_get("maxmemory-policy")["maxmemory-policy"]
    check(policy == "noeviction", "redis maxmemory-policy is noeviction", f"policy={policy}")
    worker_up = False
    for _ in range(30):
        if r.exists("arq:queue:health-check"):
            worker_up = True
            break
        time.sleep(1)
    check(worker_up, "arq worker registered its health-check key",
          f"keys={sorted(k.decode() for k in r.keys('arq:*'))}")

    failed = [name for ok, name, _ in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
