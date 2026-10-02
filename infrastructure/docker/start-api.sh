#!/bin/sh
set -eu

alembic upgrade head

exec uvicorn apps.api.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --workers 1 \
  --timeout-keep-alive 5 \
  --timeout-graceful-shutdown 20 \
  --limit-concurrency 20 \
  --limit-max-requests 1000
