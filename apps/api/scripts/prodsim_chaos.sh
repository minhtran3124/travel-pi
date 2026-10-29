#!/usr/bin/env sh
# Breaks a running prodsim stack (make prodsim-up) and checks it recovers. Exits 1 on any failure.
set -u
DC="docker compose -f docker-compose.prodsim.yml"
URL=http://localhost:8080
fail=0
ok()   { echo "PASS  $1"; }
bad()  { echo "FAIL  $1"; fail=1; }
codes() { # N requests through the proxy -> count of non-200
  n=0; i=0
  while [ $i -lt "$1" ]; do
    c=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$URL/readyz"); [ "$c" = 200 ] || n=$((n+1)); i=$((i+1))
  done; echo $n
}
wait_for() { # name, command... (up to 60 s)
  name=$1; shift; i=0
  while [ $i -lt 60 ]; do "$@" >/dev/null 2>&1 && { ok "$name"; return; }; sleep 1; i=$((i+1)); done
  bad "$name"
}

[ "$(codes 20)" = 0 ] && ok "baseline: 20/20 requests 200" || bad "baseline requests"

echo "--- stop web instance api-1 (SIGTERM, graceful)"
$DC stop -t 30 api-1 >/dev/null
[ "$(codes 40)" = 0 ] && ok "all 40 requests still 200 with api-1 down (api-2 serves)" || bad "requests failed with api-1 down"
$DC logs api-1 2>&1 | grep -qiE "shutting down|Worker exiting|Handling signal|Application shutdown" \
  && ok "api-1 logged a graceful shutdown" || bad "no graceful shutdown line in api-1 logs"
$DC start api-1 >/dev/null
wait_for "api-1 healthy again" sh -c "$DC ps api-1 | grep -q healthy"

echo "--- kill -9 the Arq worker"
$DC kill -s SIGKILL worker >/dev/null
$DC start worker >/dev/null
wait_for "worker re-registered in redis" sh -c "$DC exec -T redis redis-cli exists arq:queue:health-check | grep -q 1"

echo "--- stop redis (web must stay ready: queue falls back in-process)"
$DC stop redis >/dev/null
[ "$(codes 20)" = 0 ] && ok "readiness stays 200 with redis down" || bad "readiness broke with redis down"
$DC start redis >/dev/null
wait_for "redis answers again" sh -c "$DC exec -T redis redis-cli ping | grep -q PONG"

[ "$fail" = 0 ] && echo "chaos: all passed" || echo "chaos: FAILURES above"
exit $fail
