#!/bin/bash

# Set the paths
SPLASHSCREEN_URL="https://jellyfin.romptele.com/Branding/Splashscreen"
TARGET_DIR="/var/www/html/assets/img"
TARGET_FILE="splashscreen.png"
TEMP_FILE="/tmp/splashscreen.png"

# Create target directory if it doesn't exist
mkdir -p "$TARGET_DIR"

# Download the splashscreen image
echo "Downloading splashscreen from $SPLASHSCREEN_URL..."
if curl -s -o "$TEMP_FILE" "$SPLASHSCREEN_URL"; then
    # Check if the downloaded file is a valid image
    if file "$TEMP_FILE" | grep -q "PNG image data"; then
        # Move the new image to the target location
        mv "$TEMP_FILE" "$TARGET_DIR/$TARGET_FILE"
        echo "Splashscreen updated successfully"
        exit 0
    else
        echo "Error: Downloaded file is not a valid PNG image"
        rm "$TEMP_FILE"
        exit 1
    fi
else
    echo "Error: Failed to download splashscreen"
    exit 1
fi 