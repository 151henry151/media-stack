#!/bin/bash
# Report actual disk usage of media-storage by summing du of main directories.
# Use this to see how much space the current file tree really uses (vs. what df reports).
# Run from the server that mounts /mnt/media-storage; can take 10–30+ min on a large NFS mount.
#
# Usage: ./check-media-storage-usage.sh [output_file]
# Default output: /tmp/media-storage-usage.txt
#
set -e
OUT="${1:-/tmp/media-storage-usage.txt}"
MNT="${MEDIA_MOUNT:-/mnt/media-storage}"
echo "Measuring $MNT (this can take a while on NFS)..." >&2

total_kb=0
{
  echo "=== Media storage actual usage (du -s) ==="
  echo "Date: $(date -Iseconds)"
  echo ""

  for dir in "$MNT"/movies "$MNT"/tvshows "$MNT"/music "$MNT"/downloads "$MNT"/transcodes "$MNT"/.compress-backup "$MNT"/.compress-temp; do
    [ -d "$dir" ] || continue
    kb=$(du -s "$dir" 2>/dev/null | cut -f1)
    [ -n "$kb" ] || continue
    total_kb=$((total_kb + kb))
    gb=$(awk "BEGIN { printf \"%.1f\", $kb/1024/1024 }" 2>/dev/null || echo "?")
    echo "$(basename "$dir"): ${kb} KB (~${gb} GB)"
  done

  # Catch any other top-level dirs
  for dir in "$MNT"/*/; do
    [ -d "$dir" ] || continue
    base=$(basename "$dir")
    case "$base" in
      movies|tvshows|music|downloads|transcodes) continue ;;
      .*) continue ;;
    esac
    kb=$(du -s "$dir" 2>/dev/null | cut -f1)
    [ -n "$kb" ] || continue
    total_kb=$((total_kb + kb))
    gb=$(awk "BEGIN { printf \"%.1f\", $kb/1024/1024 }" 2>/dev/null || echo "?")
    echo "$base: ${kb} KB (~${gb} GB)"
  done

  echo ""
  total_gb=$(awk "BEGIN { printf \"%.1f\", $total_kb/1024/1024 }" 2>/dev/null || echo "?")
  echo "Total (sum of above): ${total_kb} KB (~${total_gb} GB)"
  echo ""
  echo "=== df (reported by NFS server) ==="
  df -h "$MNT" 2>/dev/null || true
} | tee "$OUT"

echo "" >&2
echo "Results written to $OUT" >&2
