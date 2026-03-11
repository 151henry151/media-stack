# AGENTS.md

## Cursor Cloud specific instructions

### Overview

This repo is infrastructure-as-code for **RompTele**, a self-hosted media server platform. It has two custom Python/FastAPI apps that are the primary development targets, plus Docker Compose configs for off-the-shelf media services.

### Custom apps (developable locally)

| App | Directory | Port | Description |
|-----|-----------|------|-------------|
| media-requests | `media-requests/` | 8002 | Chat UI for movie/TV torrent requests (Apibay + qBittorrent) |
| music-requests-chat | `music-requests-chat/` | 8003 | Chat UI for music album requests (proxies to music-requests backend on port 8001) |

Both are Python 3.12 / FastAPI apps with `requirements.txt`. Each has its own `.venv` virtualenv.

### Running the apps

```bash
# media-requests (requires JWT secret)
cd media-requests
MEDIA_REQUESTS_JWT_SECRET="dev-secret-at-least-32-characters-long" .venv/bin/uvicorn main:app --host 0.0.0.0 --port 8002

# music-requests-chat
cd music-requests-chat
MUSIC_REQUESTS_BACKEND_URL="http://127.0.0.1:8001" .venv/bin/uvicorn main:app --host 0.0.0.0 --port 8003
```

See each app's `README.md` for full environment variable documentation and `.env.example` for defaults.

### Key gotchas

- **passlib/bcrypt compatibility**: `passlib` is incompatible with `bcrypt>=4.1`. The update script pins `bcrypt==4.0.1` in the media-requests venv. If you see `AttributeError: module 'bcrypt' has no attribute '__about__'`, re-run `media-requests/.venv/bin/pip install bcrypt==4.0.1`.
- **External APIs**: The Apibay torrent search API (`apibay.org`) and music-requests backend (port 8001) are external to this repo. Chat search will return "No results found" if Apibay is unreachable. Music-requests-chat login will fail with 502 if the music-requests Docker service isn't running.
- **SQLite DB**: `media-requests/media_requests.db` is auto-created on first run with one invite code (default `welcome`). Delete it to reset.
- **No test suite or lint config**: The repo has no automated tests or linter config. Use `ruff check` for basic Python linting.
- **Docker services** (Jellyfin, qBittorrent, Radarr, Sonarr, etc.) require specific storage mounts (`/mnt/media-storage`) and a Docker network (`mynetwork`). They are not runnable in Cursor Cloud. See `README.md` and `REPRODUCTION.md` for full stack deployment.
