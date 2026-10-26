#!/usr/bin/env sh
set -e
# Migrations are opt-in: only the single deploy/pre-deploy job (or dev compose)
# sets RUN_MIGRATIONS=1. Web and worker replicas must not race on the schema.
if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
  echo "Running migrations: alembic upgrade head"
  alembic upgrade head
else
  echo "Skipping migrations (RUN_MIGRATIONS != 1)"
fi
exec "$@"
