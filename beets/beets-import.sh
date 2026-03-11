#!/bin/bash
# Beets import script - runs import on music collection
# Run as root (cron) to access /mnt/media-storage/music
# Requires Discogs token in ~/.config/beets/config.yaml

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BEET="/home/henry/beets-venv/bin/beet"
PYTHON="/home/henry/beets-venv/bin/python3"
CONFIG="/home/henry/.config/beets/config.yaml"
MUSIC_DIR="/mnt/media-storage/music"
LOG="/var/log/beets-import.log"

export BEETSDIR="${BEETSDIR:-/home/henry/.config/beets}"

LOCK_FILE="/var/run/beets-import.lock"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG"; }

# Prevent concurrent runs (e.g. 4x daily and on-new trigger)
exec 200>"$LOCK_FILE"
if ! flock -n 200; then
    log "Another beets import is already running, exiting"
    exit 0
fi

if [[ ! -d "$MUSIC_DIR" ]]; then
    log "ERROR: Music directory $MUSIC_DIR not found or not mounted"
    exit 1
fi

if [[ ! -x "$BEET" ]]; then
    log "ERROR: Beets not found at $BEET"
    exit 1
fi

log "Starting beets import on $MUSIC_DIR"
$BEET -c "$CONFIG" import -q --noresume "$MUSIC_DIR" 2>&1 | tee -a "$LOG"
log "Beets import finished (exit $?)"

log "Starting beets fetchart (album art for albums missing covers)"
$BEET -c "$CONFIG" fetchart 2>&1 | tee -a "$LOG"
log "Beets fetchart finished (exit $?)"

log "Fetching art from Cover Art Archive (MusicBrainz) for albums with mbid"
BEETS_CONFIG="$CONFIG" BEETS_LIBRARY="${BEETSDIR:-/home/henry/.config/beets}/musiclibrary.db" "$PYTHON" "$SCRIPT_DIR/fetch-coverart.py" 2>&1 | tee -a "$LOG"
log "Cover Art Archive fetch finished"

log "Embedding album art into files"
$BEET -c "$CONFIG" embedart -y 2>&1 | tee -a "$LOG"
log "Embedart finished"

log "Extracting embedded art to cover.jpg for Substreamer/Airsonic compatibility"
$BEET -c "$CONFIG" extractart -n cover '' 2>&1 | tee -a "$LOG"
log "Beets extractart finished (exit $?)"

log "Syncing compilation tags (albumartist, comp) to files for Substreamer/Airsonic"
BEETS_CONFIG="$CONFIG" "$PYTHON" "$SCRIPT_DIR/fix-compilation-tags.py" 2>&1 | tee -a "$LOG"
log "Compilation tag sync finished"

log "Removing duplicate tracks (keep best quality)"
BEETS_CONFIG="$CONFIG" "$PYTHON" "$SCRIPT_DIR/dedupe-tracks.py" --no-backup 2>&1 | tee -a "$LOG"
log "Dedupe finished"
