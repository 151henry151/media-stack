#!/bin/bash
# Deploy script: copies all files from this directory to /var/www/html, overwriting existing files

set -e

SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
DEST_DIR="/var/www/html"

if [ "$EUID" -ne 0 ]; then
  echo "Please run as root or with sudo."
  exit 1
fi

# Copy all files and directories, preserving structure, overwriting existing files
cp -a "$SRC_DIR"/* "$DEST_DIR"/

# Optionally, clean up files in DEST_DIR that no longer exist in SRC_DIR (uncomment if desired)
# rsync -av --delete "$SRC_DIR"/ "$DEST_DIR"/

echo "Deployment complete: $SRC_DIR -> $DEST_DIR" 