# Music Request

A Jellyseerr-style web app for Airsonic/Subsonic users to request music. Search artists, pick albums or discographies, find torrents via The Pirate Bay (Apibay), and add magnets to qBittorrent with one click.

## Features

- **Authentication** — Log in with your Airsonic/Subsonic credentials (verified via Subsonic API)
- **Artist search** — MusicBrainz + Deezer fallback for artist lookup with thumbnails
- **Album artwork** — Cover art from Cover Art Archive (MusicBrainz) or Deezer
- **Album or discography** — Request a single album or a full discography
- **TPB + Prowlarr search** — Search The Pirate Bay (Apibay) and all Prowlarr indexers
- **Smart filtering** — Zero-seeder torrents hidden by default with an option to reveal
- **qBittorrent integration** — Add magnets directly with category `lidarr` for Lidarr import
- **Lidarr wanted list** — When no torrents are found, add the album to Lidarr so it downloads when available

## Flow

1. Log in with your Airsonic credentials
2. Search for an artist by name
3. Choose **Album** (pick one) or **Discography** (full collection)
4. Search results show torrents; click **Add** to send a magnet to qBittorrent
5. Torrents are added with category `lidarr` for your existing pipeline (e.g. Lidarr → beets → Airsonic)

## Prerequisites

- [Docker](https://www.docker.com/) and Docker Compose
- Airsonic or Subsonic server (for auth)
- qBittorrent (for adding torrents)

## Quick Start

### Docker

```bash
# Build and run
docker build -t music-requests .
docker run -p 8000:8000 \
  -e AIRSONIC_URL=http://your-airsonic:4040 \
  -e QBIT_HOST=your-qbittorrent:8080 \
  -e QBIT_USER=admin \
  -e QBIT_PASS=your_password \
  -e QBIT_CATEGORY=lidarr \
  music-requests
```

### Docker Compose

Add to your `docker-compose.yml`:

```yaml
music-requests:
  build: ./music-requests
  ports:
    - 8001:8000
  environment:
    - AIRSONIC_URL=http://airsonic:4040
    - QBIT_HOST=qbittorrent:8080
    - QBIT_USER=${QBIT_USER}
    - QBIT_PASS=${QBIT_PASS}
    - QBIT_CATEGORY=lidarr
```

**Important:** Use environment variables or secrets for `QBIT_PASS` and similar credentials. Never commit credentials to version control.

## Configuration

| Variable        | Default                      | Description                          |
|----------------|------------------------------|--------------------------------------|
| `AIRSONIC_URL` | `http://airsonic:4040`       | Airsonic/Subsonic base URL (auth)    |
| `QBIT_HOST`    | `qbittorrent:8080`           | qBittorrent host and port            |
| `QBIT_USER`    | `admin`                      | qBittorrent Web UI username          |
| `QBIT_PASS`    | —                            | qBittorrent Web UI password          |
| `QBIT_CATEGORY`| `lidarr`                     | Category for added torrents          |
| `PROWLARR_URL` | `http://prowlarr:9696`       | Prowlarr URL (for multi-tracker search) |
| `PROWLARR_API_KEY` | —                        | Prowlarr API key (Settings → General) |
| `LIDARR_URL`   | `http://lidarr:8686`         | Lidarr URL (for "keep watch" when no torrents) |
| `LIDARR_API_KEY` | —                          | Lidarr API key (Settings → General)  |

## Reverse Proxy (Nginx)

Example config for HTTPS:

```nginx
server {
    listen 443 ssl http2;
    server_name music-requests.example.com;

    ssl_certificate /etc/letsencrypt/live/music-requests.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/music-requests.example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## Tech Stack

- **Backend:** Python, FastAPI
- **Frontend:** Vanilla HTML/CSS/JS
- **APIs:** MusicBrainz, Deezer, Apibay (TPB), Subsonic
- **Auth:** Basic Auth (credentials verified via Subsonic `ping.view`)

## Sync Trackers and Indexers

Scripts in `scripts/` keep your torrent setup populated:

| Script | Source | Destination | Purpose |
|--------|--------|-------------|---------|
| `sync_ngosang_trackers.py` | [ngosang/trackerslist](https://github.com/ngosang/trackerslist) | qBittorrent | Public announce URLs (peer discovery) |
| `sync_prowlarr_indexers.py` | Built-in list | Prowlarr | Music search sites (TPB, LimeTorrents, etc.) |
| `sync_all_trackers.py` | Both | Both | Run both syncs |

**Note:** ngosang provides *tracker announce URLs* for qBittorrent—not Prowlarr indexers. Prowlarr manages *search sites*; ngosang’s list improves peer discovery in qBittorrent.

### Running the sync

```bash
# From project root, with env vars loaded
export QBIT_HOST=qbittorrent:5080
export QBIT_USER=admin
export QBIT_PASS=your_password
export PROWLARR_URL=http://prowlarr:9696
export PROWLARR_API_KEY=your_key

# Sync ngosang trackers to qBittorrent
python scripts/sync_ngosang_trackers.py

# Sync music indexers to Prowlarr
python scripts/sync_prowlarr_indexers.py

# Or run both
python scripts/sync_all_trackers.py
```

### Docker

```bash
docker compose run --rm music-requests python scripts/sync_all_trackers.py
```

### Optional: NGOSANG_LIST

Default list is `trackers_best` (20 trackers). For more:

```bash
export NGOSANG_LIST=trackers_all  # 119 trackers
python scripts/sync_ngosang_trackers.py
```

### RuTracker (manual setup)

RuTracker has extensive music catalog but requires a free account. The sync script tries `rutracker-ru` (Cardigann); it often fails with "Forbidden" because RuTracker blocks unauthenticated requests. To add RuTracker:

1. Create a free account at [rutracker.org](https://rutracker.org)
2. In Prowlarr: **Indexers → Add Indexer** → search "RuTracker"
3. Add **RuTracker.org** (not rutracker-ru) and enter your username and password
4. Sync to Lidarr via **Indexers → Sync App Indexers**

### Cron

Add to crontab to refresh weekly:

```
0 3 * * 0 cd /path/to/media-stack && docker compose run --rm music-requests python scripts/sync_all_trackers.py
```

## Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally
uvicorn main:app --reload --port 8000
```

## Security

- Credentials are verified server-side via the Subsonic API
- All API endpoints require valid Airsonic login (Basic Auth)
- No credentials are stored; they are validated on each request
- Use HTTPS in production

## License

GPL-3.0. See [LICENSE](LICENSE) for details.
