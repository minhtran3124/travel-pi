#!/usr/bin/env sh
set -e
# Production web start path (dev compose overrides this with its own command).
# --timeout must exceed the longest LLM call (llm_timeout_seconds=120).
exec gunicorn app.main:app \
  -k uvicorn.workers.UvicornWorker \
  -w "${WEB_CONCURRENCY:-2}" \
  -b "0.0.0.0:${PORT:-8000}" \
  --timeout "${GUNICORN_TIMEOUT:-180}" \
  --graceful-timeout "${GUNICORN_GRACEFUL_TIMEOUT:-30}" \
  --keep-alive "${GUNICORN_KEEPALIVE:-75}" \
  --access-logfile -
