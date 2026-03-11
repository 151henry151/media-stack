#!/bin/bash
#
# Convert Demon Slayer seasons (S02, S03, and optionally the movie) to
# mobile-friendly MP4 (H.264/AAC, faststart). Season 1 is assumed already
# converted. Backs up originals to .compress-backup, then replaces with .mp4.
#
# Usage:
#   ./convert-demon-slayer-seasons.sh           # S02 + S03 only
#   ./convert-demon-slayer-seasons.sh --movie   # include Mugen Train movie
#   ./convert-demon-slayer-seasons.sh --dry-run # list files only, no convert
#
set -e

MEDIA_BASE="${MEDIA_BASE:-/mnt/media-storage}"
SHOW_DIR="${SHOW_DIR:-$MEDIA_BASE/tvshows/Demon Slayer - Kimetsu no Yaiba}"
BACKUP_DIR="${BACKUP_DIR:-$MEDIA_BASE/.compress-backup}"
TEMP_DIR="${TEMP_DIR:-$MEDIA_BASE/.compress-temp}"
LOG="${LOG:-/var/log/convert-demon-slayer.log}"

VIDEO_CRF="${VIDEO_CRF:-23}"
VIDEO_PRESET="${VIDEO_PRESET:-slow}"
AUDIO_BITRATE="${AUDIO_BITRATE:-192k}"

INCLUDE_MOVIE=false
DRY_RUN=false
for arg in "$@"; do
    case "$arg" in
        --movie)   INCLUDE_MOVIE=true ;;
        --dry-run) DRY_RUN=true ;;
    esac
done

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG"; }

get_duration() {
    ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$1" 2>/dev/null | head -1
}

verify_output() {
    local orig="$1" new="$2" orig_size="$3"
    [[ -f "$new" ]] || return 1
    local new_size; new_size=$(stat -c%s "$new" 2>/dev/null || echo 0)
    if [[ $((orig_size * 95 / 100)) -le $new_size ]]; then
        log "Output not small enough (orig=${orig_size} new=${new_size})"
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

convert_one() {
    local input="$1"
    local dir base output
    dir=$(dirname "$input")
    base=$(basename "$input" .mkv)
    mkdir -p "$TEMP_DIR"
    output="$TEMP_DIR/${base}.mp4"

    log "Converting: $input"
    log "  -> $output"

    local ffopts=(
        -y -i "$input"
        -map 0:v -map 0:a
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
            -map 0:v -map 0:a
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

    local final_mp4="$dir/${base}.mp4"
    log "Moving converted file to: $final_mp4"
    mv "$output" "$final_mp4" || { log "Move failed; restoring from backup"; mv "$backup_path" "$input"; return 1; }

    # Verify the file in place before removing backup (confirms not corrupt)
    if ! ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$final_mp4" &>/dev/null; then
        log "Post-replace verification failed; restoring from backup"
        rm -f "$final_mp4"
        mv "$backup_path" "$input"
        return 1
    fi

    log "Removing backup (converted file verified)"
    rm -f "$backup_path" || log "Warning: could not remove backup $backup_path"

    local new_size; new_size=$(stat -c%s "$final_mp4")
    local saved=$(( (orig_size - new_size) / 1024 / 1024 ))
    log "Done. Saved ~${saved} MB"
    return 0
}

# Collect MKVs: S02*, S03*, and optionally the movie (Mugen Train)
files=()
while IFS= read -r f; do
    [[ -f "$f" ]] && files+=("$f")
done < <(find "$SHOW_DIR" -maxdepth 1 -type f -iname '*.mkv' 2>/dev/null | while read -r f; do
    name=$(basename "$f")
    if [[ "$name" == *"S02"* ]] || [[ "$name" == *"S03"* ]]; then
        echo "$f"
    elif [[ "$INCLUDE_MOVIE" == true && "$name" == *"Mugen Train"* ]]; then
        echo "$f"
    fi
done | sort)

if [[ ${#files[@]} -eq 0 ]]; then
    log "No files to convert (S02/S03"
    $INCLUDE_MOVIE && log " / movie"
    log "). Check SHOW_DIR=$SHOW_DIR"
    exit 0
fi

log "=== convert-demon-slayer-seasons started ==="
log "Found ${#files[@]} file(s) to convert."

if [[ "$DRY_RUN" == true ]]; then
    for f in "${files[@]}"; do
        log "  [dry-run] would convert: $f"
    done
    log "=== dry run finished ==="
    exit 0
fi

failed=0
for f in "${files[@]}"; do
    if ! convert_one "$f"; then
        ((failed++)) || true
        log "Conversion failed for $f (continuing)"
    fi
done

log "=== convert-demon-slayer-seasons finished (${failed} failed) ==="
exit $failed
