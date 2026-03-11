#!/bin/bash
# Run this after the Incredibles 2 Half-SBS → 2D conversion completes.
# Verifies the temp output, backs up the original 3D file, moves 2D into place, removes 3D.
set -e
MEDIA_BASE="${MEDIA_BASE:-/mnt/media-storage}"
TEMP_DIR="${MEDIA_BASE}/.compress-temp"
BACKUP_DIR="${MEDIA_BASE}/.compress-backup"
ORIGINAL="/mnt/media-storage/movies/Incredibles 2 (2018)/Incredibles.2.2018.BluRay.3D.Remux.Half-SBS.x264.Dual..mkv"
CONVERTED_TEMP="${TEMP_DIR}/Incredibles.2.2018.1080p.2D.mp4"
FINAL="/mnt/media-storage/movies/Incredibles 2 (2018)/Incredibles.2.2018.1080p.2D.mp4"

if [[ ! -f "$CONVERTED_TEMP" ]]; then
    echo "Converted file not found: $CONVERTED_TEMP (has ffmpeg finished?)"
    exit 1
fi

orig_dur=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$ORIGINAL" 2>/dev/null || echo 0)
new_dur=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$CONVERTED_TEMP" 2>/dev/null || echo 0)
diff=${orig_dur/.*/}; diff=$((diff - ${new_dur/.*/})); diff=${diff#-}
if [[ -z "$orig_dur" || -z "$new_dur" || "$diff" -gt 2 ]]; then
    echo "Duration mismatch: original=$orig_dur new=$new_dur"
    exit 1
fi

echo "Backing up original 3D to $BACKUP_DIR"
mkdir -p "$BACKUP_DIR"
backup_path="$BACKUP_DIR/$(date +%Y%m%d)-Incredibles2-3D-$(basename "$ORIGINAL" | tr '/' '_')"
mv "$ORIGINAL" "$backup_path"

echo "Moving 2D version into place"
mv "$CONVERTED_TEMP" "$FINAL"

echo "Done. Incredibles 2 (2018) is now 2D at: $FINAL"
echo "Original 3D backup: $backup_path"
