#!/bin/bash
# Remove duplicate files in downloads that already exist in library (movies or tvshows only).
# Only removes VIDEO files (.mkv, .mp4, .avi, .m4v) that are exact duplicates of something
# under movies/ or tvshows/. Skips anything that looks like a music release (keeps seeding music).
# List must be generated first: list-download-duplicates.sh
# Usage: ./remove-download-duplicates.sh [--dry-run] [path_list]
set -e
LIST="${1:-/tmp/download_duplicate_paths.txt}"
DRY_RUN=""
[[ "$1" == "--dry-run" ]] && { DRY_RUN=1; LIST="${2:-/tmp/download_duplicate_paths.txt}"; }
[[ ! -f "$LIST" ]] && { echo "List file not found: $LIST"; exit 1; }

MOVIES_DIR="${MOVIES_DIR:-/mnt/media-storage/movies}"
TV_DIR="${TV_DIR:-/mnt/media-storage/tvshows}"

# Build set of (size basename) that exist in movies or tvshows (one-time scan)
LIBRARY_KEYS=$(mktemp)
trap 'rm -f "$LIBRARY_KEYS"' EXIT
find "$MOVIES_DIR" "$TV_DIR" -type f \( -iname "*.mkv" -o -iname "*.mp4" -o -iname "*.avi" -o -iname "*.m4v" \) -printf "%s %f\n" 2>/dev/null | sort -u > "$LIBRARY_KEYS"
echo "Library keys loaded ($(wc -l < "$LIBRARY_KEYS") entries)." >&2

# Path looks like part of a music torrent (album, FLAC, Discography, etc.) -> skip (leave music alone)
is_music_path() {
    local p="$1"
    case "$p" in
        *[Ff][Ll][Aa][Cc]*) return 0 ;;
        *[Dd]iscography*)   return 0 ;;
        *\[[Ff][Ll][Aa][Cc]*) return 0 ;;
        *\[[Mm][Pp]3*)      return 0 ;;
        *\[[Mm]p3*)         return 0 ;;
        *) return 1 ;;
    esac
}

# Only allow video extensions (safety: never remove music or other types)
is_video_file() {
    local p="$1"
    case "$p" in
        *.mkv|*.MKV|*.mp4|*.MP4|*.avi|*.AVI|*.m4v|*.M4v) return 0 ;;
        *) return 1 ;;
    esac
}

# Confirm this (size, basename) exists in our library set (movies or tvshows only)
is_duplicate_of_library() {
    local size="$1" base="$2"
    grep -Fxq "$size $base" "$LIBRARY_KEYS" 2>/dev/null
}

count=0
skipped_music=0
skipped_not_library=0
total_bytes=0
while read -r size path; do
    path="${path# }"
    [[ -z "$path" ]] && continue
    [[ ! -f "$path" ]] && continue

    base=$(basename "$path")

    # Only ever remove video files
    if ! is_video_file "$path"; then
        ((skipped_not_library++)) || true
        continue
    fi

    # Leave music torrents completely alone
    if is_music_path "$path"; then
        ((skipped_music++)) || true
        continue
    fi

    # Double-check: must exist in movies or tvshows with same size
    if ! is_duplicate_of_library "$size" "$base"; then
        ((skipped_not_library++)) || true
        continue
    fi

    ((count++)) || true
    total_bytes=$((total_bytes + size))
    if [[ -n "$DRY_RUN" ]]; then
        echo "Would remove: $path"
    else
        rm -f "$path" && echo "Removed: $path" || echo "Failed: $path" >&2
    fi
done < "$LIST"
echo "---" >&2
echo "Removed (or would remove): $count files" >&2
echo "Skipped (music path): $skipped_music" >&2
echo "Skipped (not in library / non-video): $skipped_not_library" >&2
echo "Total size freed (GB): $((total_bytes / 1000000000))" >&2
