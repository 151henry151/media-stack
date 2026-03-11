#!/usr/bin/env bash
cd "$(dirname "$0")"
export MUSIC_REQUESTS_BACKEND_URL="${MUSIC_REQUESTS_BACKEND_URL:-http://127.0.0.1:8001}"
export PORT="${PORT:-8003}"
exec .venv/bin/uvicorn main:app --host 127.0.0.1 --port "$PORT"
