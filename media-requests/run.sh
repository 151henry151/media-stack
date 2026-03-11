#!/usr/bin/env bash
# Run the media-requests app (requests.romptele.com). Uses .venv in this directory.
# For production, run under systemd or a process manager so it stays up.
set -e
cd "$(dirname "$0")"
export MEDIA_REQUESTS_JWT_SECRET="${MEDIA_REQUESTS_JWT_SECRET:?Set MEDIA_REQUESTS_JWT_SECRET}"
export PORT="${PORT:-8002}"
exec .venv/bin/uvicorn main:app --host 127.0.0.1 --port "$PORT"
