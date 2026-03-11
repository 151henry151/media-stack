# Media Requests (requests.romptele.com)

Chat-style web UI to request movies or TV shows. The bot searches Apibay (The Pirate Bay), picks a suitable torrent (movies &lt;5GB when possible, TV smallest full season, ≥1 seeder), and after you confirm adds it to qBittorrent (Radarr/Sonarr category).

## Features

- **Invite-only registration** – users need a valid invite code to register.
- **JWT auth** – login returns a token; store it (e.g. in `localStorage`) and send `Authorization: Bearer <token>` on API requests.
- **Chat flow** – say what you want (e.g. “Add The Matrix” or “I want Breaking Bad season 1”); bot replies with one candidate (name, size, seeders) and asks for confirmation; on “yes” the torrent is added to the download manager.

## Run locally (no Docker)

```bash
cd /home/henry/webserver/media-stack/media-requests
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export MEDIA_REQUESTS_JWT_SECRET="your-secret"
export QBIT_HOST="localhost:5080"   # or qbittorrent:5080 if qBittorrent is in Docker on same host
export QBIT_USER=admin
export QBIT_PASS=your-qbit-password
uvicorn main:app --host 0.0.0.0 --port 8002
```

Then open http://localhost:8002 (or use nginx to proxy `requests.romptele.com` to port 8002).

## Run with Docker

Build and run (map port 8002 on host to 8000 in container):

```bash
docker build -t media-requests .
docker run -d --name media-requests \
  -p 8002:8000 \
  -e MEDIA_REQUESTS_JWT_SECRET="your-secret" \
  -e QBIT_HOST="qbittorrent:5080" \
  -e QBIT_USER=admin \
  -e QBIT_PASS=your-password \
  media-requests
```

If qBittorrent runs in the same Docker network, use `QBIT_HOST=qbittorrent:5080`. If it runs on the host, use `QBIT_HOST=host.docker.internal:5080` (or the host’s IP).

## Nginx

Config is in `/home/henry/webserver/nginx/conf.d/requests.romptele.com.conf` (proxy to `127.0.0.1:8002`). Get a certificate:

```bash
sudo certbot certonly --nginx -d requests.romptele.com
sudo nginx -t && sudo systemctl reload nginx
```

## First run / invite codes

On first start the app creates the SQLite DB and, if the invite table is empty, seeds one code from `MEDIA_REQUESTS_FIRST_INVITE` (default `welcome`). Change that env var or add more codes via the API after logging in:

```bash
curl -X POST https://requests.romptele.com/api/admin/invite \
  -H "Authorization: Bearer YOUR_JWT" \
  -H "Content-Type: application/json" \
  -d '{"code": "friends-2025"}'
```

## Environment

| Variable | Default | Description |
|----------|---------|-------------|
| `MEDIA_REQUESTS_DB` | `./media_requests.db` | SQLite path (users, invite codes). |
| `MEDIA_REQUESTS_JWT_SECRET` | (required in prod) | Secret for signing JWTs. |
| `MEDIA_REQUESTS_FIRST_INVITE` | `welcome` | First invite code if DB has none. |
| `QBIT_HOST` | `localhost:5080` | qBittorrent host:port. |
| `QBIT_USER` / `QBIT_PASS` | admin / admin123 | qBittorrent credentials. |

## Headless agent (optional)

The project does **not** use the Cursor headless agent to add torrents. It talks to qBittorrent and Apibay directly from the FastAPI app. If you later want to trigger headless agents for other tasks, see `/home/henry/cursor-agent-script/HEADLESS-AGENT-SETUP.md`.
