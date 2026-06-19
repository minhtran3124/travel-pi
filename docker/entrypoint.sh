#!/usr/bin/env sh
set -e
# Postgres path: bring the schema to head before serving. (No-op if tables are
# already at head.) SQLite/dev path self-creates in lifespan, so this is still
# safe.
echo "Running migrations: alembic upgrade head"
alembic upgrade head
exec "$@"
