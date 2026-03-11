#!/bin/bash
# Run full beets import when new content is detected
# Triggers: (1) Lidarr imported and touched BEETS_IMPORT_PENDING, (2) manually added albums (mtime check)
# Cooldown: 30 min between change-triggered runs to avoid thrashing

FLAG_FILE="${BEETS_IMPORT_PENDING:-/var/run/beets-import-pending}"
COOLDOWN_FILE="/var/run/beets-import-on-new.last"
COOLDOWN_SEC=1800
MUSIC_DIR="/mnt/media-storage/music"
IMPORT_SCRIPT="/home/henry/webserver/media-stack/beets/beets-import.sh"
LOG="/var/log/beets-import.log"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [on-new] $*" | tee -a "$LOG"; }

# (1) Lidarr flag - run immediately (Lidarr sets this when it imports)
if [[ -f "$FLAG_FILE" ]]; then
    log "Lidarr import detected (flag file) - running full beets import"
    rm -f "$FLAG_FILE"
    "$IMPORT_SCRIPT"
    date +%s > "$COOLDOWN_FILE"
    exit 0
fi

# (2) mtime check - new content from manual add or other sources
if [[ ! -d "$MUSIC_DIR" ]]; then
    exit 0
fi

# Respect cooldown
if [[ -f "$COOLDOWN_FILE" ]]; then
    last=$(cat "$COOLDOWN_FILE" 2>/dev/null)
    if [[ -n "$last" && "$last" =~ ^[0-9]+$ ]]; then
        elapsed=$(($(date +%s) - last))
        if [[ $elapsed -lt $COOLDOWN_SEC ]]; then
            exit 0
        fi
    fi
fi

# Any directory (artist or album) modified in last 20 min? Exclude root with -mindepth 1
recent=$(find "$MUSIC_DIR" -mindepth 1 -maxdepth 2 -type d -mmin -20 2>/dev/null | head -5)
if [[ -z "$recent" ]]; then
    exit 0
fi

log "New content detected (mtime) - running full beets import"
"$IMPORT_SCRIPT"
date +%s > "$COOLDOWN_FILE"
