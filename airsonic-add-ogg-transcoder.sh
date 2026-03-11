#!/bin/bash
# Add OGG transcoder to Airsonic and assign to Substreamer
# Requires: Airsonic STOPPED. Backs up DB, runs SQL via HSQL SqlTool, then you restart.
#
# Usage: run as root or with docker access
#   ./airsonic-add-ogg-transcoder.sh
#
# Per workspace rules: script will NOT stop containers without explicit confirmation.

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DB_VOLUME="_data"
# Docker volume path - adjust if your Docker root differs
VOLUME_ROOT="/var/lib/docker/volumes/media-stack_airsonic-advanced-config"
DB_PATH="${VOLUME_ROOT}/${DB_VOLUME}/db"
DB_FILE="${DB_PATH}/airsonic"
BACKUP_DIR="${VOLUME_ROOT}/${DB_VOLUME}/db-backup-ogg-$(date +%Y%m%d-%H%M%S)"
HSQL_LIB="/tmp/airsonic-hsqldb"
HSQL_JAR="${HSQL_LIB}/hsqldb-2.7.2.jar"
SQLTOOL_JAR="${HSQL_LIB}/sqltool-2.7.2.jar"
HSQL_URL="https://repo1.maven.org/maven2/org/hsqldb/hsqldb/2.7.2/hsqldb-2.7.2.jar"
SQLTOOL_URL="https://repo1.maven.org/maven2/org/hsqldb/sqltool/2.7.2/sqltool-2.7.2.jar"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

# Check if Airsonic is running
if docker ps --format '{{.Names}}' 2>/dev/null | grep -q '^airsonic-advanced$'; then
    log "Airsonic container is RUNNING. It must be stopped to modify the database safely."
    echo ""
    read -p "Stop airsonic-advanced now? (yes/no): " confirm
    if [[ "$confirm" != "yes" ]]; then
        log "Aborted. Stop Airsonic manually, then run this script again."
        exit 1
    fi
    log "Stopping airsonic-advanced..."
    cd "$SCRIPT_DIR" || exit 1
    docker compose stop airsonic-advanced
    log "Waiting for container to fully stop..."
    sleep 5
fi

if ! docker ps -a --format '{{.Names}}' 2>/dev/null | grep -q '^airsonic-advanced$'; then
    log "ERROR: airsonic-advanced container not found. Is docker-compose/media-stack set up?"
    exit 1
fi

if [[ ! -d "$DB_PATH" ]]; then
    log "ERROR: Database path not found: $DB_PATH"
    exit 1
fi

if [[ -f "${DB_FILE}.lck" ]]; then
    log "ERROR: Database lock file exists. Airsonic may still be running or did not shut down cleanly."
    exit 1
fi

# Backup
log "Backing up database to $BACKUP_DIR"
cp -a "$DB_PATH" "$BACKUP_DIR"
log "Backup done."

# Download HSQL jars if needed
mkdir -p "$HSQL_LIB"
if [[ ! -f "$HSQL_JAR" ]]; then
    log "Downloading HSQLDB..."
    curl -sL -o "$HSQL_JAR" "$HSQL_URL" || { log "ERROR: Failed to download HSQL"; exit 1; }
fi
if [[ ! -f "$SQLTOOL_JAR" ]]; then
    log "Downloading SqlTool..."
    curl -sL -o "$SQLTOOL_JAR" "$SQLTOOL_URL" || { log "ERROR: Failed to download SqlTool"; exit 1; }
fi

# Run SQL
SQL_FILE="${SCRIPT_DIR}/airsonic-add-ogg-transcoder.sql"
log "Running SQL from $SQL_FILE"
java -cp "${HSQL_JAR}:${SQLTOOL_JAR}" org.hsqldb.cmdline.SqlTool --inlineRc "url=jdbc:hsqldb:file:${DB_FILE},user=SA,password=" "$SQL_FILE"
log "SQL executed successfully."

# Reminder to start
log "Done. Start Airsonic with: cd $SCRIPT_DIR && docker compose start airsonic-advanced"
echo ""
read -p "Start airsonic-advanced now? (yes/no): " start_confirm
if [[ "$start_confirm" == "yes" ]]; then
    cd "$SCRIPT_DIR" || exit 1
    docker compose start airsonic-advanced
    log "Airsonic started."
fi
