#!/bin/bash
#
# Nightly media compression: convert oversized movies/TV to MP4 (H.264/AAC)
# Runs only 3am-7am. Processes one file at a time; after each, checks time and
# continues with the next if before 7am. In-progress conversions run to completion
# even past 7am. Lock prevents multiple instances.
#
MEDIA_BASE="${MEDIA_BASE:-/mnt/media-storage}"
MOVIES_DIR="${MOVIES_DIR:-$MEDIA_BASE/movies}"
TV_DIR="${TV_DIR:-$MEDIA_BASE/tvshows}"
MIN_SIZE_GB="${MIN_SIZE_GB:-3}"
TEMP_DIR="${TEMP_DIR:-$MEDIA_BASE/.compress-temp}"
BACKUP_DIR="${BACKUP_DIR:-$MEDIA_BASE/.compress-backup}"
LOG="${LOG:-/var/log/compress-media-nightly.log}"
LOCK_FILE="${LOCK_FILE:-/var/run/compress-media-nightly.lock}"
# Shared with replace-movie-with-smaller: paths listed here are "in use" and must not be picked by the other script.
CLAIMED_FILE="${MEDIA_STACK_CLAIMED_FILE:-/var/run/media-stack-claimed.txt}"
START_HOUR=3
END_HOUR=7
VIDEO_CRF="${VIDEO_CRF:-23}"
VIDEO_PRESET="${VIDEO_PRESET:-slow}"
AUDIO_BITRATE="${AUDIO_BITRATE:-192k}"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG"; }

in_window() {
    local h; h=$(date +%H | sed 's/^0//')
    [[ "$h" -ge "$START_HOUR" && "$h" -lt "$END_HOUR" ]]
}

# Single instance: non-blocking flock
exec 200>"$LOCK_FILE"
flock -n 200 || { log "Already running (lock held); exiting."; exit 0; }

# One-shot / manual run: set FORCE_RUN_ONE=1 to bypass time window and run one conversion.
# Optionally set CONVERT_THIS_FILE=/path/to/file to convert that file instead of the largest.
MAX_CONVERSIONS="${MAX_CONVERSIONS:-0}"
run_one="${FORCE_RUN_ONE:-0}"
current_hour=$(date +%H | sed 's/^0//')
if [[ "$run_one" -ne 1 ]]; then
    if [[ "$current_hour" -lt "$START_HOUR" || "$current_hour" -ge "$END_HOUR" ]]; then
        log "Outside window ($START_HOUR:00-$END_HOUR:00); exiting."
        exit 0
    fi
fi

find_videos() {
    find "$1" -type f \( -iname "*.mkv" -o -iname "*.mp4" -o -iname "*.avi" -o -iname "*.m4v" -o -iname "*.mov" \) \
        2>/dev/null | while read -r f; do
        size=$(stat -c%s "$f" 2>/dev/null || echo 0)
        echo "$size $f"
    done | sort -rn
}

# Pick largest file >= MIN_SIZE_GB. Pass paths to exclude (e.g. previously failed this run).
pick_largest() {
    local min_bytes=$((MIN_SIZE_GB * 1024 * 1024 * 1024))
    local candidates=""
    local exclude=("$@")
    for dir in "$MOVIES_DIR" "$TV_DIR"; do
        [[ -d "$dir" ]] || continue
        while read -r size path; do
            [[ "$size" -ge "$min_bytes" ]] || break
            [[ "$path" == *".compress-backup"* ]] && continue
            [[ "$path" == *".compress-temp"* ]] && continue
            local skip=0
            for ex in "${exclude[@]}"; do
                [[ -n "$ex" && "$path" == "$ex" ]] && { skip=1; break; }
            done
            [[ $skip -eq 1 ]] && continue
            candidates+="$size $path"$'\n'
        done < <(find_videos "$dir")
    done
    echo "$candidates" | sort -rn | head -1
}

get_duration() {
    ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$1" 2>/dev/null | head -1
}

verify_output() {
    local orig="$1" new="$2" orig_size="$3"
    [[ -f "$new" ]] || return 1
    local new_size; new_size=$(stat -c%s "$new" 2>/dev/null || echo 0)
    if [[ $((orig_size * 95 / 100)) -le $new_size ]]; then
        log "Output not smaller enough (orig=${orig_size} new=${new_size})"
        return 1
    fi
    local orig_dur new_dur
    orig_dur=$(get_duration "$orig") || return 1
    new_dur=$(get_duration "$new") || return 1
    [[ -z "$orig_dur" || -z "$new_dur" ]] && return 1
    local diff=${orig_dur/.*/}
    diff=$((diff - ${new_dur/.*/}))
    diff=${diff#-}
    [[ "$diff" -le 2 ]] || { log "Duration mismatch orig=$orig_dur new=$new_dur"; return 1; }
    if ! ffprobe -v error -show_streams "$new" &>/dev/null; then
        log "ffprobe reported errors on output"
        return 1
    fi
    return 0
}

compress_file() {
    local input="$1"
    local dir base ext output
    dir=$(dirname "$input")
    base=$(basename "$input")
    ext="${base##*.}"
    base="${base%.*}"
    mkdir -p "$TEMP_DIR"
    output="$TEMP_DIR/${base}.compressed.mp4"

    log "Converting: $input"
    log "  -> $output"

    # Map only first video stream (0:v:0) to avoid MJPEG/thumbnail streams breaking encoder
    local ffopts=(
        -y -i "$input"
        -map 0:v:0 -map 0:a
        -map 0:s? -c:s mov_text
        -c:v libx264 -crf "$VIDEO_CRF" -preset "$VIDEO_PRESET"
        -c:a aac -b:a "$AUDIO_BITRATE"
        -movflags +faststart
        "$output"
    )

    if ! ffmpeg -v warning -stats "${ffopts[@]}" >>"$LOG" 2>&1; then
        log "Retrying without subtitles (source may have image subs)"
        ffopts=(
            -y -i "$input"
            -map 0:v:0 -map 0:a
            -c:v libx264 -crf "$VIDEO_CRF" -preset "$VIDEO_PRESET"
            -c:a aac -b:a "$AUDIO_BITRATE"
            -movflags +faststart
            "$output"
        )
        if ! ffmpeg -v warning -stats "${ffopts[@]}" >>"$LOG" 2>&1; then
            log "FFmpeg failed"
            rm -f "$output"
            return 1
        fi
    fi

    local orig_size; orig_size=$(stat -c%s "$input")
    if ! verify_output "$input" "$output" "$orig_size"; then
        log "Verification failed; keeping original"
        rm -f "$output"
        return 1
    fi

    mkdir -p "$BACKUP_DIR"
    local backup_path="$BACKUP_DIR/$(date +%Y%m%d)-$(basename "$dir")-$(basename "$input" | tr '/' '_')"
    log "Backing up original to: $backup_path"
    mv "$input" "$backup_path" || { log "Backup failed"; rm -f "$output"; return 1; }

    log "Replacing with compressed file"
    mv "$output" "$input" || { log "Replace failed; restoring from backup"; mv "$backup_path" "$input"; return 1; }

    # Verify the file in place before removing backup (confirms not corrupt)
    if ! ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$input" &>/dev/null; then
        log "Post-replace verification failed; restoring from backup"
        mv "$input" "$TEMP_DIR/replace-failed.$$.mp4"
        mv "$backup_path" "$input"
        rm -f "$TEMP_DIR/replace-failed.$$.mp4"
        return 1
    fi

    log "Removing backup (converted file verified)"
    rm -f "$backup_path" || log "Warning: could not remove backup $backup_path"

    local new_size; new_size=$(stat -c%s "$input")
    local saved=$(( (orig_size - new_size) / 1024 / 1024 ))
    log "Done. Saved ~${saved} MB"
    return 0
}

log "=== compress-media-nightly started ==="

conversions_done=0
failed_paths=()
while [[ "$run_one" -ne 1 ]] && in_window || { [[ "$run_one" -eq 1 ]] && [[ "$conversions_done" -lt 1 ]]; }; do
    # Exclude paths claimed by replace-movie-with-smaller (or a previous compress run)
    claimed_paths=()
    if [[ -f "$CLAIMED_FILE" ]]; then
        while IFS= read -r p; do [[ -n "$p" ]] && claimed_paths+=("$p"); done < "$CLAIMED_FILE"
    fi
    if [[ -n "${CONVERT_THIS_FILE:-}" && -f "${CONVERT_THIS_FILE:-}" ]]; then
        candidate="$(stat -c%s "$CONVERT_THIS_FILE") $CONVERT_THIS_FILE"
    else
        candidate=$(pick_largest "${failed_paths[@]}" "${claimed_paths[@]}")
    fi
    if [[ -z "$candidate" ]]; then
        if [[ ${#failed_paths[@]} -gt 0 ]]; then
            log "No more candidates (${#failed_paths[@]} failed this run); stopping."
        else
            log "No files >= ${MIN_SIZE_GB} GB found."
        fi
        break
    fi

    read -r size path <<< "$candidate"
    size_gb=$((size / 1024 / 1024 / 1024))
    log "Next candidate: $path (${size_gb} GB)"

    # Claim this path so replace-movie-with-smaller won't pick it
    echo "$path" >> "$CLAIMED_FILE"
    if compress_file "$path"; then
        ((conversions_done++)) || true
    else
        if [[ -n "${CONVERT_THIS_FILE:-}" ]]; then
            log "Requested file failed; exiting."
            break
        fi
        failed_paths+=("$path")
        log "Skipping this file for rest of run; will try next largest."
    fi
    # Release claim so other script can pick this path in future
    [[ -f "$CLAIMED_FILE" ]] && grep -v -Fx "$path" "$CLAIMED_FILE" > "$CLAIMED_FILE.tmp" && mv "$CLAIMED_FILE.tmp" "$CLAIMED_FILE"

    if [[ "$run_one" -eq 1 ]] || { [[ "$MAX_CONVERSIONS" -gt 0 ]] && [[ "$conversions_done" -ge "$MAX_CONVERSIONS" ]]; }; then
        log "One-shot run: stopping after ${conversions_done} conversion(s)."
        break
    fi
done

if ! in_window; then
    log "Past ${END_HOUR}:00; stopping (no new conversions)."
fi

log "=== compress-media-nightly finished ==="
exit 0
