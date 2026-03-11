#!/bin/bash
# Wrapper for lidarr-torrent-import.py - run via cron
# Processes completed qBittorrent torrents (category: lidarr) into music library

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG="/var/log/lidarr-torrent-import.log"
# Use beets venv (has qbittorrent-api); fallback to system python
PYTHON="${PYTHON:-/home/henry/beets-venv/bin/python3}"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG"; }

# qBittorrent credentials
export QBIT_HOST="${QBIT_HOST:-localhost:5080}"
export QBIT_USER="${QBIT_USER:-admin}"
export QBIT_PASS="${QBIT_PASS:-admin123}"
export MUSIC_DIR="${MUSIC_DIR:-/mnt/media-storage/music}"
export DOWNLOADS_DIR="${DOWNLOADS_DIR:-/mnt/media-storage/downloads}"

# Optional: Airsonic scan after import (set AIRSONIC_PASS to enable)
# export AIRSONIC_URL="http://localhost:4040"
# export AIRSONIC_USER="admin"
# export AIRSONIC_PASS="your-password"

log "Starting lidarr torrent import"
"$PYTHON" "$SCRIPT_DIR/lidarr-torrent-import.py" 2>&1 | tee -a "$LOG"

# Run dedupe after import - new torrents (especially discographies) can add duplicate tracks
DEDUPE_SCRIPT="$SCRIPT_DIR/../beets/dedupe-tracks.py"
if [[ -f "$DEDUPE_SCRIPT" ]]; then
    log "Running dedupe after import"
    BEETS_CONFIG="${BEETS_CONFIG:-/home/henry/.config/beets/config.yaml}" \
        "$PYTHON" "$DEDUPE_SCRIPT" --no-backup 2>&1 | tee -a "$LOG"
fi

log "Finished (exit $?)"
