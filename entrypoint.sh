#!/usr/bin/env sh
set -eu
echo "Starting sensor hub..."
exec /app/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 "$@"
