# Airsonic OGG Transcoder Setup (Substreamer Gapless Playback)

OGG Vorbis transcoding provides **gapless playback** when streaming to Substreamer (and other clients). MP3/AAC transcoding causes noticeable pauses between tracks; OGG does not.

## What Was Set Up

1. **OGG transcoder** – ffmpeg converts to OGG Vorbis (quality 4, ~128 kbps equivalent)
2. **Assign to Substreamer** – All existing players with TYPE containing "Substreamer" get the OGG transcoder
3. **Default for new users** – `DEFAULT_ACTIVE=TRUE` means every **new** player (including new Substreamer users on Android/iPhone) automatically gets OGG transcoding enabled

## Option A: Automated Script (recommended)

Run the script when you're ready to apply the changes. It will:

- Ask for confirmation before stopping Airsonic
- Back up the database
- Add the OGG transcoder and assign it to Substreamer players
- Offer to restart Airsonic

```bash
cd /home/henry/webserver/media-stack
./airsonic-add-ogg-transcoder.sh
```

**Prerequisites:** Java 11+ on the host, `curl`, docker/compose access. Airsonic will be stopped during the operation.

## Option B: Manual Steps (via Airsonic Web UI)

If you prefer to configure via the UI at https://music.romptele.com:

### 1. Add the OGG transcoder

- **Settings → Transcoding**
- **Add transcoder**
- **Name:** `ffmpeg - OGG (gapless)`
- **Source formats:** `*` (or `flac mp3 m4a aac`)
- **Target format:** `ogg`
- **Step 1:** `ffmpeg -re -i %s -map 0:a:0 -c:a libvorbis -q:a 4 -f ogg -`
- Leave Step 2 and Step 3 blank
- **Default active:** ✓ (so new players get it)
- Save

### 2. Assign to Substreamer players

- **Settings → Players**
- For each Substreamer player, click **Edit**
- Under **Transcodings**, enable **ffmpeg - OGG (gapless)**
- Save

### 3. New Substreamer users

When `Default active` is checked on the OGG transcoder, **new players** (including new Substreamer users) automatically receive that transcoder. No extra configuration is needed.

## Substreamer behavior

Substreamer can request OGG when the server supports it. With the OGG transcoder enabled for Substreamer players, streaming will use OGG for gapless playback.

## Files

- `airsonic-add-ogg-transcoder.sh` – Script that stops Airsonic, runs SQL, and restarts
- `airsonic-add-ogg-transcoder.sql` – SQL to add transcoder and player assignments
- Database backup – Stored under the Airsonic config volume as `db-backup-ogg-YYYYMMDD-HHMMSS`
