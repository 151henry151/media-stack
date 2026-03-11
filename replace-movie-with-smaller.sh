#!/bin/bash
# Wrapper: run replace-movie-with-smaller.py with a Python env that has requests and qbittorrent-api.
# Usage: ./replace-movie-with-smaller.sh [--dry-run] [--add-only] [--min-size-gb N] [--movie-path /path/to/movie.mkv]
#
# If qBittorrent runs in Docker with /mnt/media-storage/downloads:/downloads, set:
#   export QBIT_SAVE_PATH_REPLACEMENT=/downloads/replacement-movies
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="${QBIT_PYTHON:-/home/henry/beets-venv/bin/python}"
if [[ ! -x "$PYTHON" ]]; then
  echo "Python not found: $PYTHON (set QBIT_PYTHON)" >&2
  exit 1
fi
exec "$PYTHON" "$SCRIPT_DIR/replace-movie-with-smaller.py" "$@"
