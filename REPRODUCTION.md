# Reproducing the RompTele Media Server

This document describes how to reproduce the full media server setup from scratch (excluding the actual media files). The configuration lives in two repositories:

- **media-stack** (this repo): Docker Compose stack, scripts, cron jobs, media-requests app, and automation.
- **webserver**: Nginx configs for `*.romptele.com`; config files are symlinked from `/etc/nginx/conf.d/` to the webserver repo.

---

## 1. Prerequisites

- **Host**: Linux server with Docker, Docker Compose v2+, and Nginx on the host (not in Docker for this setup).
- **Storage**: A mount or directory used as the media root, e.g. `/mnt/media-storage`. Expected layout:
  - `movies/` – Radarr-managed movies
  - `tvshows/` – Sonarr-managed TV
  - `music/` – Lidarr/Airsonic music library
  - `downloads/` – qBittorrent download directory (Radarr/Sonarr import from here)
  - `playlists/`, `podcasts/` – optional (Airsonic)
- **Network**: Docker network `mynetwork` (see below).
- **DNS**: Domains (e.g. `jellyfin.romptele.com`, `requests.romptele.com`) pointing to the server IP.

---

## 2. Clone Repositories

```bash
git clone https://github.com/151henry151/media-stack.git
cd media-stack
# Optional: clone webserver for nginx configs
git clone https://github.com/151henry151/my-webserver-setup.git ../webserver
```

---

## 3. Docker Network and Stack

Create the Docker network (required before bringing up the stack):

```bash
docker network create --subnet 172.20.0.0/16 mynetwork
```

Create a `.env` in the media-stack root with at least:

- `QBIT_USER`, `QBIT_PASS` – qBittorrent Web UI (and for music-requests / media-requests if they talk to qBittorrent).
- `TMDB_APIKEY` – for Jellyseerr (create at https://www.themoviedb.org/settings/api).
- Optional: `PROWLARR_API_KEY`, `LIDARR_API_KEY`, `VPN_*` if using VPN, etc.

Deploy the stack (no-VPN example):

```bash
docker compose --profile no-vpn up -d
```

With VPN, use `--profile vpn` and set `OPENVPN_USER`, `OPENVPN_PASSWORD`, `RADARR_STATIC_CONTAINER_IP`, `SONARR_STATIC_CONTAINER_IP` as in `README.md`.

---

## 4. Nginx (Host)

Nginx runs on the host. Configs are kept in the webserver repo and symlinked:

```bash
# Example: symlink all conf.d files from repo to system
sudo ln -sf /path/to/webserver/nginx/conf.d/requests.romptele.com.conf /etc/nginx/conf.d/
sudo ln -sf /path/to/webserver/nginx/conf.d/jellyfin.romptele.com.conf /etc/nginx/conf.d/
# ... repeat for radarr, sonarr, qbittorrent, prowlarr, jellyseerr, lidarr,
#    music.romptele.com, music-requests.romptele.com, ampache7.romptele.com,
#    admin.romptele.com, grafana.romptele.com, romptele.com
```

Obtain SSL certificates (e.g. Let’s Encrypt):

```bash
sudo certbot certonly --webroot -w /path/to/webroot -d requests.romptele.com
# Repeat for each domain, or use certbot --nginx
```

Test and reload:

```bash
sudo nginx -t && sudo systemctl reload nginx
```

Media-related server names in this setup typically include:  
`jellyfin.romptele.com`, `radarr.romptele.com`, `sonarr.romptele.com`, `qbittorrent.romptele.com`, `prowlarr.romptele.com`, `jellyseerr.romptele.com`, `lidarr.romptele.com`, `music.romptele.com`, `music-requests.romptele.com`, `requests.romptele.com`, `admin.romptele.com`, `romptele.com`, `ampache7.romptele.com`, `grafana.romptele.com`.

---

## 5. Host Services (Non-Docker)

These run on the host and are part of the “media server” setup.

### 5.1 Media-requests app (requests.romptele.com)

Chat UI for requesting movies/TV via Apibay + qBittorrent.

- **Location**: `media-stack/media-requests/`
- **Run**: Use the systemd unit; install and start:

  ```bash
  cd media-stack/media-requests
  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
  cp .env.example .env
  # Edit .env: set MEDIA_REQUESTS_JWT_SECRET (and optionally QBIT_HOST, QBIT_USER, QBIT_PASS)
  sudo cp media-requests.service /etc/systemd/system/
  sudo systemctl daemon-reload
  sudo systemctl enable --now media-requests
  ```

- Nginx proxies `requests.romptele.com` to `http://127.0.0.1:8002`.

### 5.2 Cron Jobs

Install cron files under `/etc/cron.d/` (or equivalent) so the following run as configured:

| File | Purpose |
|------|--------|
| `compress-media-nightly-cron` | Nightly compression of large movies/TV (uses `compress-media-nightly.sh`) |
| `replace-movie-with-smaller-cron` | Replace large movies with smaller Apibay releases (uses `replace-movie-with-smaller.sh`) |
| `qbit-remove-errored-cron` | Remove errored/missing-file torrents from qBittorrent (uses `qbit-remove-errored-torrents.sh`) |
| `airsonic-watchdog-cron` | Airsonic watchdog (uses `airsonic-watchdog.sh`) |
| `lidarr/lidarr-import-cron` | Lidarr torrent import (uses `lidarr-torrent-import.sh`) |
| `beets/beets-cron` | Beets import (uses `beets/beets-import.sh` or similar) |

Scripts expect to be run from the media-stack repo root (or paths adjusted). Wrappers (e.g. `replace-movie-with-smaller.sh`) use a Python env that has `requests`, `qbittorrent-api`; point `QBIT_PYTHON` at a venv that has those (e.g. `media-requests/.venv/bin/python`).

### 5.3 One-off / Helper Scripts

- `check-media-storage-usage.sh` – Report disk usage for media directories.
- `list-download-duplicates.sh` / `remove-download-duplicates.sh` – Find/remove duplicates between `downloads/` and library.
- `add-attack-on-titan-seasons.py` – Example script to add specific TV seasons via Apibay; run with a Python that has `requests` and `qbittorrent-api`.
- Lidarr: `lidarr/add-discography-torrents.py`, `lidarr/lidarr-torrent-import.py` (and `.sh`).
- Beets: under `beets/` (import, dedupe, etc.).
- Airsonic: `airsonic-add-ogg-transcoder.sh`, `airsonic-add-ogg-transcoder.sql`, `airsonic-watchdog.sh`.

---

## 6. Configuration Summary

- **Radarr / Sonarr**: Download client = qBittorrent (host `qbittorrent`, port `5080`; if VPN, use VPN service name). Categories: `radarr` (movies), `tv-sonarr` (TV). Library paths under `/mnt/media-storage` (or your media root).
- **qBittorrent**: Save path for movies/TV typically ` /downloads` (maps to host `.../downloads`). Categories `radarr` and `tv-sonarr` so Radarr/Sonarr pick up completed downloads.
- **Media-requests**: Uses same qBittorrent (e.g. `QBIT_HOST=qbittorrent:5080` when app runs on host; or `localhost:5080` if qBittorrent is on host). Adds torrents with categories `radarr` or `tv-sonarr`.
- **Jellyfin**: Libraries point at `/media/movies`, `/media/tvshows`, etc. (container paths). Transcode/cache dirs as in `docker-compose.yml`.
- **Jellyseerr**: Configure Radarr, Sonarr, Jellyfin, Prowlarr per Jellyseerr docs; URLs use Docker service names.

---

## 7. What Is Not in the Repo

- Actual media files (movies, TV, music).
- `.env` files (create from examples; keep secrets out of git).
- Nginx SSL private keys and certs (obtain with certbot or your CA).
- Database files or runtime state (e.g. `ldap/data/lock.mdb`, Jellyfin/Radarr/Sonarr config volumes).
- `media-requests/media_requests.db` (created at first run; backup separately if needed).

---

## 8. Quick Checklist After Clone

1. Create `/mnt/media-storage` (or your media root) and subdirs: `movies`, `tvshows`, `music`, `downloads`, etc.
2. Create Docker network `mynetwork`.
3. Add `.env` in media-stack with `QBIT_*`, `TMDB_APIKEY`, and any VPN/API keys.
4. Run `docker compose --profile no-vpn up -d` (or `--profile vpn` with static IPs).
5. Symlink nginx configs from webserver repo to `/etc/nginx/conf.d/` and obtain certs; reload nginx.
6. Set up media-requests (venv, `.env`, systemd unit).
7. Install cron jobs for compress-nightly, replace-movie, qbit-remove-errored, airsonic-watchdog, lidarr-import, beets if used.
8. Configure Radarr, Sonarr, Prowlarr, Jellyseerr, Jellyfin via their UIs (and Lidarr/Airsonic if used).

After that, the server is reproducible except for media content and secrets.
