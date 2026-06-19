#!/usr/bin/env sh
# Thin entry point for non-Make users: build + start the app + Postgres stack.
exec docker compose up --build "$@"
