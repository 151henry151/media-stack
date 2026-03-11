#!/bin/bash
# Wrapper: run qbit-remove-errored-torrents.py with a Python env that has qbittorrent-api.
# Usage: ./qbit-remove-errored-torrents.sh [--dry-run]
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="${QBIT_PYTHON:-/home/henry/beets-venv/bin/python}"
if [[ ! -x "$PYTHON" ]]; then
  echo "Python not found: $PYTHON (set QBIT_PYTHON)" >&2
  exit 1
fi
exec "$PYTHON" "$SCRIPT_DIR/qbit-remove-errored-torrents.py" "$@"
