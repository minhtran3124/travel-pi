#!/usr/bin/env sh
# Run the test suite in Docker against an isolated Postgres, then tear down.
docker compose -f docker-compose.test.yml up --build \
  --abort-on-container-exit --exit-code-from tests
docker compose -f docker-compose.test.yml down -v
