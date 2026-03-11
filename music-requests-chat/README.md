# Music Requests Chat

Chatbot UI for [music-requests](https://github.com/151henry151/music-requests): request albums via natural language. Same backend (artist/album search, torrents, YouTube rip, playlist/archive import) with a conversational interface.

- **Auth**: Airsonic credentials (same as music-requests).
- **Flow**: Say e.g. “Add Dark Side of the Moon by Pink Floyd”; the bot searches artists, finds the album, searches torrents, and offers “add 1” or a YouTube rip if no torrents.
- **URLs**: Paste a YouTube or archive.org URL to get a preview and “rip” as an album.

## Run locally

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
# Edit .env: MUSIC_REQUESTS_BACKEND_URL must point at the music-requests API (e.g. http://127.0.0.1:8001)
./run.sh
```

Then open http://127.0.0.1:8003 (or set `PORT`).

## Deploy (systemd)

1. Create venv and install deps (as above).
2. Copy unit and enable:

```bash
sudo cp music-requests-chat.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now music-requests-chat
```

3. Point nginx at `http://127.0.0.1:8003` for `music-requests.romptele.com`.

The **music-requests** backend must be running (e.g. Docker on port 8001). Set `MUSIC_REQUESTS_BACKEND_URL` in `.env` to that URL.
