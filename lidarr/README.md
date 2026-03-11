# Lidarr + qBittorrent Music Import

Imports completed music torrents from qBittorrent (category: `lidarr`) into the music library for Airsonic and Beets.

## How it works

1. **qBittorrent** – Torrents with category `lidarr` download to `/mnt/media-storage/downloads`
2. **Import script** – Runs periodically, finds 100% complete `lidarr` torrents
3. **Beets** – Copies to `music/_Import/`, runs `beet import -m` to tag, fetch art, and move into `Artist/Album/`
4. **Airsonic** – Optional scan triggered after imports
5. **Tracking** – Processed torrents are tagged `beets_imported` so they are not imported again

Torrents are not modified or removed; they stay in the downloads folder for seeding.

## Setup

### 1. Install qbittorrent-api

```bash
pip install qbittorrent-api
# Or with beets venv:
/home/henry/beets-venv/bin/pip install qbittorrent-api
```

### 2. qBittorrent credentials

**Required** – Edit `lidarr-torrent-import.sh` or set env vars. The default password is often changed:

- `QBIT_HOST` – default `localhost:5080`
- `QBIT_USER` – default `admin`
- `QBIT_PASS` – **set your actual qBittorrent Web UI password**

### 3. qBittorrent category

Assign category `lidarr` to your music torrents (you already did this).

### 4. Lidarr (optional)

Add qBittorrent as a download client in Lidarr (Settings → Download Clients) with category `lidarr` for future Lidarr-managed downloads. The import script also works for manually added magnets.

### 5. Cron

Run every 15–30 minutes:

```bash
# Create cron
sudo cp /home/henry/webserver/media-stack/lidarr/lidarr-import-cron /etc/cron.d/lidarr-torrent-import
```

## Manual run

```bash
/home/henry/webserver/media-stack/lidarr/lidarr-torrent-import.sh
```

## Airsonic rescan

To trigger an Airsonic media scan after each import, set in the script or env:

```bash
export AIRSONIC_URL="http://localhost:4040"   # or your Airsonic URL
export AIRSONIC_USER="admin"
export AIRSONIC_PASS="your-airsonic-password"
```

## Paths

- Music library: `/mnt/media-storage/music`
- Downloads: `/mnt/media-storage/downloads`
- Staging: `music/_Import/` (cleaned after beets processes)
