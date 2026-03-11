"""
Music Requests Chat – chatbot wrapper for music-requests.romptele.com.
Same backend (artist/album search, TPB, YouTube rip, playlist/archive import) with a chat UI.
Auth: Airsonic credentials; session holds creds and forwards Basic auth to backend.
"""
from __future__ import annotations

import base64
import os
import re
import uuid
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

BACKEND_URL = os.environ.get("MUSIC_REQUESTS_BACKEND_URL", "http://127.0.0.1:8001").rstrip("/")
SESSION_COOKIE = "music_chat_session"
SESSION_STORE: dict[str, dict] = {}  # session_id -> { username, password, pending_*, ... }


def _auth_headers(username: str, password: str) -> dict[str, str]:
    raw = f"{username}:{password}"
    b64 = base64.b64encode(raw.encode()).decode()
    return {"Authorization": f"Basic {b64}"}


async def _backend_get(path: str, params: dict | None, username: str, password: str) -> dict | list:
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(
            f"{BACKEND_URL}{path}",
            params=params or {},
            headers=_auth_headers(username, password),
        )
    if r.status_code == 401:
        raise HTTPException(status_code=401, detail="Session expired; please log in again.")
    r.raise_for_status()
    return r.json()


async def _backend_post(path: str, json: dict, username: str, password: str) -> dict:
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(
            f"{BACKEND_URL}{path}",
            json=json,
            headers=_auth_headers(username, password),
        )
    if r.status_code == 401:
        raise HTTPException(status_code=401, detail="Session expired; please log in again.")
    r.raise_for_status()
    return r.json() if r.content else {}


def _parse_add_album(msg: str) -> tuple[str | None, str | None]:
    """Extract 'album' and 'artist' from phrases like 'add Dark Side by Pink Floyd', 'album X by Y'."""
    msg = msg.strip()
    for prefix in ("add ", "get ", "want ", "find ", "album ", "request "):
        if msg.lower().startswith(prefix):
            msg = msg[len(prefix):].strip()
    # "Album Title by Artist Name" or "Artist Name - Album Title"
    by_match = re.search(r"\bby\b(.+)$", msg, re.I)
    if by_match:
        before, after = msg[: by_match.start()].strip(), by_match.group(1).strip()
        if before and after:
            return before, after
    dash = re.search(r"^(.+?)\s*[-–—]\s*(.+)$", msg)
    if dash:
        return dash.group(2).strip(), dash.group(1).strip()
    return None, None


def _normalize(msg: str) -> str:
    msg = msg.strip().lower()
    if len(msg) >= 2 and msg[0] == msg[-1] and msg[0] in "'\"":
        msg = msg[1:-1].strip()
    return msg


def _parse_artist_list(msg: str) -> list[str] | None:
    """If message looks like a list of artist names (newlines or commas), return non-empty names; else None."""
    raw = (msg or "").strip()
    if not raw or re.match(r"https?://", raw):
        return None
    # Split by newlines or commas
    parts = re.split(r"[\n,]+", raw)
    names = [p.strip() for p in parts if p.strip()]
    # Require at least 2 names to treat as list; skip if it looks like "Album by Artist"
    if len(names) < 2:
        return None
    # Don't treat "Add X by Y" as a list
    if raw.lower().startswith(("add ", "get ", "want ", "album ", "request ")) and " by " in raw.lower():
        return None
    return names


# --- Pydantic ---
class LoginRequest(BaseModel):
    username: str
    password: str


class ChatRequest(BaseModel):
    message: str


# --- App ---
app = FastAPI(title="Music Requests Chat")
static_dir = Path(__file__).resolve().parent / "static"
if static_dir.is_dir():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


def get_session(request: Request) -> tuple[str, dict]:
    sid = request.cookies.get(SESSION_COOKIE)
    if not sid or sid not in SESSION_STORE:
        raise HTTPException(status_code=401, detail="Not logged in")
    return sid, SESSION_STORE[sid]


@app.get("/", response_class=HTMLResponse)
async def index():
    return FileResponse(static_dir / "index.html")


@app.post("/api/login")
async def login(req: LoginRequest, response: Response):
    # Verify with backend (which pings Airsonic)
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(
                f"{BACKEND_URL}/api/login",
                json={"username": req.username.strip(), "password": req.password},
            )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not reach music server: {e}")
    if r.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid Airsonic credentials")
    sid = uuid.uuid4().hex
    SESSION_STORE[sid] = {
        "username": req.username.strip(),
        "password": req.password,
        "pending_torrents": [],
        "pending_yt": None,
        "artist_name": "",
        "album_title": "",
    }
    response.set_cookie(SESSION_COOKIE, sid, httponly=True, samesite="lax", max_age=7 * 24 * 3600)
    return {"ok": True, "username": req.username.strip()}


@app.get("/api/me")
async def me(request: Request):
    """Return current user if session valid."""
    _, session = get_session(request)
    return {"username": session["username"]}


@app.post("/api/logout")
async def logout(response: Response, request: Request):
    sid = request.cookies.get(SESSION_COOKIE)
    if sid and sid in SESSION_STORE:
        del SESSION_STORE[sid]
    response.delete_cookie(SESSION_COOKIE)
    return {"ok": True}


@app.post("/api/chat")
async def chat(req: ChatRequest, request: Request):
    _, session = get_session(request)
    username = session["username"]
    password = session["password"]
    msg = (req.message or "").strip()
    if not msg:
        return {"reply": "Send a message to request music. Try: \"Add Dark Side of the Moon by Pink Floyd\", \"Search artist Radiohead\", or paste a list of artist names (one per line or comma-separated) to add discography for each. You can also paste a YouTube or archive.org URL to rip an album. Note: it may be a day or two before your music appears on the server."}

    msg_lower = _normalize(msg)
    pending_torrents = session.get("pending_torrents") or []
    pending_yt = session.get("pending_yt")

    # Confirm torrent: "add 1", "yes", "add first"
    if pending_torrents and re.match(r"^(add\s*)?([1-9]\d*)$", msg_lower):
        idx = int(re.search(r"[1-9]\d*", msg_lower).group())
        if 1 <= idx <= len(pending_torrents):
            t = pending_torrents[idx - 1]
            magnet = t.get("magnet")
            if magnet:
                await _backend_post("/api/add-torrent", {"magnet": magnet}, username, password)
                session["pending_torrents"] = []
                return {"reply": "I've added that torrent to the download queue. It may be a day or two before it appears in your music library.", "attachments": []}
    if pending_torrents and re.match(r"\b(yes|add it|add 1|first one)\b", msg_lower):
        t = pending_torrents[0]
        magnet = t.get("magnet")
        if magnet:
            await _backend_post("/api/add-torrent", {"magnet": magnet}, username, password)
            session["pending_torrents"] = []
            return {"reply": "Added to the download queue. It may be a day or two before it appears in your library.", "attachments": []}

    # Reject / cancel
    if re.match(r"\b(no|cancel|different)\b", msg_lower) and (pending_torrents or pending_yt):
        session["pending_torrents"] = []
        session["pending_yt"] = None
        return {"reply": "No problem. What would you like to add instead?", "attachments": []}

    # Confirm YouTube rip
    if pending_yt and re.match(r"\b(rip|yes|rip it|from youtube)\b", msg_lower):
        url = pending_yt.get("url")
        artist = pending_yt.get("artist") or session.get("artist_name", "")
        album = pending_yt.get("album") or session.get("album_title", "")
        if url and artist and album:
            result = await _backend_post(
                "/api/rip-youtube",
                {"url": url, "artist": artist, "album": album, "year": pending_yt.get("year")},
                username,
                password,
            )
            session["pending_yt"] = None
            job_id = result.get("job_id", "")
            return {"reply": f"I've started ripping from YouTube (job {job_id}). It may be a day or two before it appears in your library. You can check progress on the main Music Request page if needed.", "attachments": [], "job_id": job_id}

    # Paste URL: playlist or archive
    if re.match(r"https?://", msg):
        url = msg.strip()
        if "youtube.com" in url or "youtu.be" in url or "music.youtube" in url:
            try:
                preview = await _backend_get("/api/playlist-preview", {"url": url}, username, password)
                artist = (preview.get("suggested_artist") or preview.get("artist") or "").strip()
                album = (preview.get("suggested_album") or preview.get("album") or preview.get("title") or "").strip()
                session["pending_yt"] = {"url": url, "artist": artist, "album": album}
                return {"reply": f"I found a playlist/video. Suggested: **{artist}** – **{album}**. Reply **rip** to rip it as an album and add to your library.", "attachments": []}
            except Exception as e:
                return {"reply": f"Could not load that URL: {e}", "attachments": []}
        if "archive.org" in url:
            try:
                preview = await _backend_get("/api/archive-preview", {"url": url}, username, password)
                artist = (preview.get("suggested_artist") or preview.get("artist") or "").strip()
                album = (preview.get("suggested_album") or preview.get("album") or preview.get("title") or "").strip()
                session["pending_yt"] = {"url": url, "artist": artist, "album": album}
                return {"reply": f"I found an archive.org item: **{artist}** – **{album}**. Reply **rip** to download and add to your library.", "attachments": []}
            except Exception as e:
                return {"reply": f"Could not load that URL: {e}", "attachments": []}

    # Pasted list of artist names: add discography (or best torrent) for each
    artist_list = _parse_artist_list(msg)
    if artist_list:
        max_artists = 30
        names = artist_list[:max_artists]
        added: list[str] = []
        not_found: list[str] = []
        no_torrent: list[str] = []
        errors: list[str] = []
        for name in names:
            name = name.strip()
            if not name:
                continue
            try:
                data = await _backend_get("/api/artists", {"q": name, "source": "torrent"}, username, password)
                artists = data.get("artists") or []
                if not artists:
                    not_found.append(name)
                    continue
                artist_name = artists[0].get("name", name)
                tpb = await _backend_get("/api/search-tpb", {"q": artist_name}, username, password)
                results = tpb.get("results") or []
                torrents = [r for r in results if int(r.get("seeders") or 0) >= 1]
                if not torrents:
                    no_torrent.append(artist_name)
                    continue
                magnet = torrents[0].get("magnet")
                if magnet:
                    await _backend_post("/api/add-torrent", {"magnet": magnet}, username, password)
                    added.append(artist_name)
            except Exception as e:
                errors.append(f"{name}: {e}")
        reply_parts = []
        if added:
            reply_parts.append(f"Added discography (or first available torrent) for **{len(added)}** artist(s): {', '.join(added)}.")
        if no_torrent:
            reply_parts.append(f"No seeded torrent found for: {', '.join(no_torrent)}.")
        if not_found:
            reply_parts.append(f"Artist not found: {', '.join(not_found)}.")
        if errors:
            reply_parts.append(f"Errors: {'; '.join(errors[:5])}{'…' if len(errors) > 5 else ''}.")
        if len(artist_list) > max_artists:
            reply_parts.append(f"(Processed first {max_artists} of {len(artist_list)} names.)")
        reply_parts.append("Note: it may be a day or two before your music appears on the server.")
        return {"reply": " ".join(reply_parts), "attachments": []}

    # "Search artist X"
    if msg_lower.startswith("search artist ") or msg_lower.startswith("artist "):
        q = msg_lower.replace("search artist ", "").replace("artist ", "").strip()
        if len(q) < 2:
            return {"reply": "Type at least 2 characters to search for an artist.", "attachments": []}
        try:
            data = await _backend_get("/api/artists", {"q": q, "source": "torrent"}, username, password)
            artists = data.get("artists") or []
        except Exception as e:
            return {"reply": str(e), "attachments": []}
        if not artists:
            return {"reply": f"No artists found for \"{q}\". Try a different search.", "attachments": []}
        session["pending_artists"] = artists
        return {"reply": f"I found {len(artists)} artist(s). Say **add [album] by [artist]** with the exact artist name to request an album, or paste a list of artist names to add discography for each.", "attachments": [{"type": "artists", "artists": artists[:15]}]}

    # "Add [album] by [artist]" or "album X by Y"
    album, artist = _parse_add_album(msg)
    if not artist or not album:
        return {"reply": "To request an album, say something like: **Add Dark Side of the Moon by Pink Floyd** or **album Kid A by Radiohead**. You can also paste a list of artist names (one per line or comma-separated) to add discography for each, or paste a YouTube or archive.org URL to rip an album.", "attachments": []}

    # Resolve artist
    try:
        data = await _backend_get("/api/artists", {"q": artist, "source": "torrent"}, username, password)
        artists = data.get("artists") or []
    except Exception as e:
        return {"reply": str(e), "attachments": []}
    if not artists:
        return {"reply": f"I couldn't find an artist matching \"{artist}\". Try **Search artist {artist}** to see options.", "attachments": []}
    # Pick first artist (or best match)
    chosen = artists[0]
    artist_id = chosen.get("id", "")
    artist_name = chosen.get("name", artist)
    session["artist_name"] = artist_name
    session["album_title"] = album

    # Get albums
    try:
        albums_data = await _backend_get(f"/api/albums/{artist_id}", None, username, password)
        albums = albums_data.get("albums") or []
    except Exception as e:
        return {"reply": str(e), "attachments": []}
    album_match = None
    for a in albums:
        if album.lower() in (a.get("title") or "").lower():
            album_match = a
            break
    if not album_match and albums:
        album_match = albums[0]

    # Search TPB
    tpb_q = f"{artist_name} {album}"
    try:
        tpb = await _backend_get("/api/search-tpb", {"q": tpb_q}, username, password)
        results = tpb.get("results") or []
    except Exception as e:
        return {"reply": str(e), "attachments": []}

    # Filter to reasonable torrents (at least 1 seeder)
    torrents = [r for r in results if int(r.get("seeders") or 0) >= 1][:10]
    if torrents:
        session["pending_torrents"] = torrents
        album_cover = (album_match or {}).get("image") if album_match else None
        lines = [f"{i+1}. {t['name'][:70]} — {t['seeders']} seeders, {int(t.get('size',0))/1024**3:.2f} GB" for i, t in enumerate(torrents[:5])]
        reply = f"I found **{artist_name}** – **{album}**"
        if album_cover:
            reply += f". Reply **add 1** to add the first torrent, or **add 2**, **add 3**, etc."
        else:
            reply += f". Reply **add 1** (or **add 2**, **add 3**) to add one of these torrents:"
        return {"reply": reply, "attachments": [{"type": "torrents", "torrents": torrents[:5], "album_image": album_cover}, {"type": "artists", "artists": [chosen] }]}

    # No torrents: offer YouTube
    try:
        yt = await _backend_get("/api/search-youtube", {"q": tpb_q, "mode": "album", "artist": artist_name, "album": album}, username, password)
        yt_results = yt.get("results") or []
    except Exception as e:
        return {"reply": f"No torrents found for **{album}** by **{artist_name}**. YouTube search failed: {e}", "attachments": []}
    if not yt_results:
        return {"reply": f"No torrents or YouTube results for **{album}** by **{artist_name}**. Try a different spelling or search.", "attachments": []}
    best = yt_results[0]
    session["pending_yt"] = {"url": best.get("url") or best.get("id", ""), "artist": artist_name, "album": album}
    if not session["pending_yt"]["url"].startswith("http"):
        session["pending_yt"]["url"] = f"https://www.youtube.com/watch?v={best.get('id', '')}"
    reply = f"No torrents found for **{album}** by **{artist_name}**, but I can rip it from YouTube. Reply **rip** to start."
    return {"reply": reply, "attachments": [{"type": "artists", "artists": [chosen] }, {"type": "album_cover", "image": (album_match or {}).get("image") if album_match else None}]}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8003")))
