#!/bin/bash
# Airsonic watchdog - checks every 5 min (via cron), restarts container if down/502
# Cooldown: 6 minutes after restart to allow ~5 min startup time

CHECK_URL="${AIRSONIC_CHECK_URL:-http://127.0.0.1:4040/login}"
COOLDOWN_SEC=360
COOLDOWN_FILE="/var/run/airsonic-watchdog.last-restart"
LOG="/var/log/airsonic-watchdog.log"
COMPOSE_DIR="/home/henry/webserver/media-stack"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG"; }

# Check cooldown - skip restart if we restarted recently
if [[ -f "$COOLDOWN_FILE" ]]; then
    last_restart=$(cat "$COOLDOWN_FILE" 2>/dev/null)
    if [[ -n "$last_restart" && "$last_restart" =~ ^[0-9]+$ ]]; then
        elapsed=$(( $(date +%s) - last_restart ))
        if [[ $elapsed -lt $COOLDOWN_SEC ]]; then
            log "Skipping check (cooldown: ${elapsed}s since last restart, need ${COOLDOWN_SEC}s)"
            exit 0
        fi
    fi
fi

# Health check
http_code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 10 --max-time 15 "$CHECK_URL" 2>/dev/null)
curl_exit=$?

if [[ "$http_code" == "200" ]]; then
    exit 0
fi

# Down: 502, 503, connection failure, timeout, etc.
log "Airsonic appears down (HTTP $http_code, curl exit $curl_exit) - restarting container"
date +%s > "$COOLDOWN_FILE"

cd "$COMPOSE_DIR" || { log "ERROR: cd $COMPOSE_DIR failed"; exit 1; }
docker compose restart airsonic-advanced >> "$LOG" 2>&1
log "Restart initiated (container takes ~5 min to become ready)"
