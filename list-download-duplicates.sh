#!/bin/bash
# List files in downloads that duplicate library (same size + basename as in movies/tvshows).
# Usage: ./list-download-duplicates.sh [output_file]
# Output: one line per duplicate: SIZE PATH (bytes and full path in downloads).
set -e
DUPLICATE_KEYS="${DUPLICATE_KEYS:-/tmp/duplicate_sizename.txt}"
OUT="${1:-/tmp/download_duplicate_paths.txt}"
: > "$OUT"
if [[ ! -f "$DUPLICATE_KEYS" ]]; then
    echo "Run duplicate check first to create $DUPLICATE_KEYS" >&2
    exit 1
fi
declare -A keys
while IFS= read -r line; do keys["$line"]=1; done < "$DUPLICATE_KEYS"
echo "Loaded ${#keys[@]} duplicate keys. Scanning downloads..." >&2
while read -r size path; do
    base=$(basename "$path")
    [[ -n "${keys[$size $base]}" ]] && echo "$size $path" >> "$OUT"
done < <(find /mnt/media-storage/downloads -type f \( -iname "*.mkv" -o -iname "*.mp4" -o -iname "*.avi" -o -iname "*.m4v" \) -printf "%s %p\n" 2>/dev/null)
echo "Wrote duplicate paths to $OUT" >&2
wc -l "$OUT" >&2
