"""
Music Request App - Jellyseerr-like flow for Airsonic users.
- Auth via Subsonic API (ping)
- Artist search via MusicBrainz
- Album list via MusicBrainz
- TPB search via Apibay
- Add magnet to qBittorrent (category: lidarr)

Copyright (C) 2026  Music Request contributors
This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""
import asyncio
import os
import re
import urllib.parse
from contextlib import asynccontextmanager

import httpx
import qbittorrentapi
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Config from env
AIRSONIC_URL = os.environ.get("AIRSONIC_URL", "https://music.romptele.com").rstrip("/")
QBIT_HOST = os.environ.get("QBIT_HOST", "qbittorrent:5080")
QBIT_USER = os.environ.get("QBIT_USER", "admin")
QBIT_PASS = os.environ.get("QBIT_PASS", "adminadmin")
CATEGORY = os.environ.get("QBIT_CATEGORY", "lidarr")
PROWLARR_URL = os.environ.get("PROWLARR_URL", "http://prowlarr:9696").rstrip("/")
PROWLARR_API_KEY = os.environ.get("PROWLARR_API_KEY", "")
LIDARR_URL = os.environ.get("LIDARR_URL", "http://lidarr:8686").rstrip("/")
LIDARR_API_KEY = os.environ.get("LIDARR_API_KEY", "")

MUSICBRAINZ_BASE = "https://musicbrainz.org/ws/2"
APIBAY_BASE = "https://apibay.org"
DEEZER_BASE = "https://api.deezer.com"
USER_AGENT = "MusicRequests/1.0 (https://music-requests.romptele.com)"


# --- Models ---
class LoginRequest(BaseModel):
    username: str
    password: str


class AddTorrentRequest(BaseModel):
    magnet: str


class AddToLidarrRequest(BaseModel):
    album_id: str  # MusicBrainz release-group ID
    artist_name: str
    album_title: str


# --- Auth: verify Airsonic credentials via Subsonic ping ---
async def verify_airsonic(username: str, password: str) -> bool:
    """Verify credentials against Airsonic/Subsonic ping.view endpoint."""
    params = {"u": username, "p": password, "v": "1.15.0", "c": "music-requests"}
    url = f"{AIRSONIC_URL}/rest/ping.view"
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(url, params=params)
    if r.status_code != 200:
        return False
    # Subsonic returns XML; "ok" in body means success
    return "status=\"ok\"" in r.text or '"status":"ok"' in r.text


def get_auth_header(authorization: str | None = Header(default=None, alias="Authorization")) -> tuple[str, str]:
    """Extract Basic Auth from Authorization header. Returns (username, password)."""
    if not authorization or not authorization.startswith("Basic "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization")
    import base64
    try:
        decoded = base64.b64decode(authorization[6:]).decode("utf-8")
        if ":" not in decoded:
            raise ValueError()
        u, p = decoded.split(":", 1)
        return u, p
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid Authorization")


# --- MusicBrainz ---
async def mb_search_artists(query: str) -> list[dict]:
    url = f"{MUSICBRAINZ_BASE}/artist/"
    params = {"query": query, "fmt": "json", "limit": 25}
    headers = {"User-Agent": USER_AGENT}
    async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
        r = await client.get(url, params=params)
    r.raise_for_status()
    data = r.json()
    return data.get("artists", [])


# --- Deezer (artist images) ---
def _norm_name(s: str) -> str:
    return "".join(c.lower() for c in s if c.isalnum() or c.isspace()).strip()


async def deezer_artist_images(query: str) -> dict[str, list[str]]:
    """Fetch artist images from Deezer. Returns norm_name -> list of image URLs in Deezer order.
    Multiple artists with same name get distinct images by position (avoids wrong image for e.g. Sublime band vs Sublime Afropop)."""
    url = f"{DEEZER_BASE}/search/artist"
    params = {"q": query, "limit": 25}
    try:
        headers = {"User-Agent": USER_AGENT}
        async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
            r = await client.get(url, params=params)
        r.raise_for_status()
        data = r.json()
    except Exception:
        return {}
    result: dict[str, list[str]] = {}
    for a in data.get("data", []):
        name = a.get("name")
        img = a.get("picture_medium") or a.get("picture_small")
        if name and img and "/artist//" not in img:
            norm = _norm_name(name)
            result.setdefault(norm, []).append(img)
    return result


async def deezer_search_artists(query: str) -> list[dict]:
    """Fallback: fetch artists from Deezer when MusicBrainz is unreachable."""
    url = f"{DEEZER_BASE}/search/artist"
    params = {"q": query, "limit": 25}
    try:
        headers = {"User-Agent": USER_AGENT}
        async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
            r = await client.get(url, params=params)
        r.raise_for_status()
        data = r.json()
    except Exception:
        return []
    out = []
    for a in data.get("data", []):
        name = a.get("name")
        if not name:
            continue
        did = a.get("id")
        img = a.get("picture_medium") or a.get("picture_small") or ""
        if img and "/artist//" in img:
            img = ""
        out.append({"id": f"deezer:{did}", "name": name, "type": "Artist", "image": img or None})
    return out


async def deezer_get_albums(deezer_id: str) -> list[dict]:
    """Fetch albums for a Deezer artist."""
    url = f"{DEEZER_BASE}/artist/{deezer_id}/albums"
    params = {"limit": 100}
    try:
        headers = {"User-Agent": USER_AGENT}
        async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
            r = await client.get(url, params=params)
        r.raise_for_status()
        data = r.json()
    except Exception:
        return []
    out = []
    for a in data.get("data", []):
        title = a.get("title")
        if not title:
            continue
        rg_type = a.get("record_type", "album")
        if rg_type not in ("album", "ep", "single"):
            continue
        date = (a.get("release_date") or "")[:4]
        cover = a.get("cover_medium") or a.get("cover_small") or None
        out.append({"id": a.get("id"), "title": title, "type": rg_type.title(), "date": date, "cover": cover})
    return out


async def mb_get_release_groups(artist_id: str) -> list[dict]:
    url = f"{MUSICBRAINZ_BASE}/release-group/"
    params = {"artist": artist_id, "fmt": "json", "limit": 100}
    headers = {"User-Agent": USER_AGENT}
    async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
        r = await client.get(url, params=params)
    r.raise_for_status()
    data = r.json()
    return data.get("release-groups", [])


# --- Apibay (TPB) ---
async def apibay_search(query: str) -> list[dict]:
    """Search TPB via Apibay. Returns list of {id, name, info_hash, seeders, leechers, size, added}."""
    url = f"{APIBAY_BASE}/q.php"
    params = {"q": query, "cat": "0"}
    headers = {"User-Agent": USER_AGENT}
    async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
        r = await client.get(url, params=params)
    r.raise_for_status()
    data = r.json()
    if not data or (isinstance(data, list) and len(data) == 1 and data[0].get("id") == "0"):
        return []
    return data if isinstance(data, list) else []


def info_hash_to_magnet(info_hash: str, name: str) -> str:
    """Build magnet link from Apibay info_hash and name."""
    dn = urllib.parse.quote(name)
    return f"magnet:?xt=urn:btih:{info_hash}&dn={dn}"


# --- Prowlarr (multi-indexer search) ---
_MAGNET_RE = re.compile(r'magnet:\?[^"\'<>\s]+')


async def _resolve_download_url_to_magnet(url: str) -> str | None:
    """Fetch a page (e.g. RuTracker viewtopic) and extract magnet link. Used when Prowlarr returns downloadUrl but no magnet."""
    if not url or not url.startswith("http"):
        return None
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
            r = await client.get(url)
        r.raise_for_status()
        raw = r.content
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            try:
                text = raw.decode("cp1251")  # RuTracker uses windows-1251
            except (UnicodeDecodeError, LookupError):
                text = raw.decode("latin-1")  # fallback, never fails
    except Exception:
        return None
    m = _MAGNET_RE.search(text)
    return m.group(0) if m else None


async def prowlarr_search(query: str) -> list[dict]:
    """Search Prowlarr (all indexers). Returns same shape as apibay_search. Category 3000 = music."""
    if not PROWLARR_URL or not PROWLARR_API_KEY:
        return []
    url = f"{PROWLARR_URL}/api/v1/search"
    params = {"query": query, "categories": 3000}
    headers = {"User-Agent": USER_AGENT, "X-Api-Key": PROWLARR_API_KEY}
    try:
        async with httpx.AsyncClient(timeout=60.0, headers=headers) as client:
            r = await client.get(url, params=params)
        r.raise_for_status()
        data = r.json()
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    # First pass: items with magnet go to out; items needing resolution go to needs_resolve
    needs_resolve: list[tuple[dict, str, str | None]] = []  # (item, url_to_fetch, fallback_prowlarr_url)
    out: list[dict] = []
    seen_hashes: set[str] = set()
    for item in data:
        ih = (item.get("infoHash") or item.get("info_hash") or "").lower().strip()
        if ih in seen_hashes:
            continue
        if ih:
            seen_hashes.add(ih)
        name = item.get("title") or item.get("name") or "Unknown"
        magnet = item.get("magnetUrl") or item.get("magnet_url") or item.get("magnet")
        if not magnet and ih:
            magnet = info_hash_to_magnet(ih, name)
        if not magnet:
            # RuTracker etc: Prowlarr returns guid (direct) or downloadUrl (proxy) but no magnet; resolve by fetching page
            guid = item.get("guid") or item.get("link")
            download_url = item.get("downloadUrl") or item.get("download_url")
            if guid and "rutracker" in str(guid).lower():
                # Try direct RuTracker URL first; fallback to Prowlarr proxy if direct fetch fails
                needs_resolve.append((item, guid, download_url))
            continue
        seeders = int(item.get("seeders", 0) or 0)
        leechers = int(item.get("leechers", 0) or 0)
        size = int(item.get("size", 0) or 0)
        out.append({
            "name": name,
            "seeders": seeders,
            "leechers": leechers,
            "size": size,
            "added": 0,
            "magnet": magnet,
        })
    # Resolve download URLs to magnets in parallel
    if needs_resolve:
        async def _resolve_one(item: dict, url: str, fallback: str | None) -> str | None:
            magnet = await _resolve_download_url_to_magnet(url)
            if not magnet and fallback and fallback.startswith("http"):
                # Fallback: Prowlarr proxy (works when direct RuTracker fetch fails, e.g. server blocked)
                magnet = await _resolve_download_url_to_magnet(fallback)
            return magnet

        resolved = await asyncio.gather(*[_resolve_one(it, u, fb) for it, u, fb in needs_resolve])
        for (item, _url, _fb), magnet in zip(needs_resolve, resolved):
            if magnet:
                name = item.get("title") or item.get("name") or "Unknown"
                seeders = int(item.get("seeders", 0) or 0)
                leechers = int(item.get("leechers", 0) or 0)
                size = int(item.get("size", 0) or 0)
                out.append({
                    "name": name,
                    "seeders": seeders,
                    "leechers": leechers,
                    "size": size,
                    "added": 0,
                    "magnet": magnet,
                })
    return out


async def search_all_trackers(query: str) -> list[dict]:
    """Search Apibay (TPB) and Prowlarr in parallel; merge and dedupe by info_hash."""
    apibay_task = apibay_search(query)
    prowlarr_task = prowlarr_search(query)
    apibay_results, prowlarr_results = await asyncio.gather(apibay_task, prowlarr_task)
    seen: set[str] = set()
    merged = []
    for r in apibay_results:
        mag = r.get("magnet", "")
        ih = ""
        if "btih:" in mag:
            try:
                ih = mag.split("btih:")[1].split("&")[0].lower()[:40]
            except Exception:
                pass
        if ih and ih in seen:
            continue
        if ih:
            seen.add(ih)
        merged.append(r)
    for r in prowlarr_results:
        mag = r.get("magnet", "")
        ih = ""
        if "btih:" in mag:
            try:
                ih = mag.split("btih:")[1].split("&")[0].lower()[:40]
            except Exception:
                pass
        if ih and ih in seen:
            continue
        if ih:
            seen.add(ih)
        merged.append(r)
    return merged


# --- Lidarr (add album to wanted) ---
async def lidarr_add_album(album_id: str) -> bool:
    """Add album to Lidarr's wanted list by MusicBrainz release-group ID. Returns True on success."""
    if not LIDARR_URL or not LIDARR_API_KEY:
        return False
    headers = {"User-Agent": USER_AGENT, "X-Api-Key": LIDARR_API_KEY}
    try:
        lookup_url = f"{LIDARR_URL}/api/v1/album/lookup"
        async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
            r = await client.get(lookup_url, params={"term": f"lidarr:{album_id}"})
        r.raise_for_status()
        data = r.json()
        album = data[0] if isinstance(data, list) and data else (data if isinstance(data, dict) else None)
        if not album:
            return False
        album["monitored"] = True
        album["addOptions"] = {"searchForNewAlbum": True}
        add_url = f"{LIDARR_URL}/api/v1/album"
        async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
            r2 = await client.post(add_url, json=album)
        if r2.status_code in (200, 201):
            return True
        if r2.status_code == 409:
            return True  # Already exists
        return False
    except Exception:
        return False


# --- qBittorrent ---
def _qbit_client() -> qbittorrentapi.Client:
    host, _, port = QBIT_HOST.partition(":")
    port = int(port) if port else 5080
    return qbittorrentapi.Client(
        host=host or "localhost",
        port=port,
        username=QBIT_USER,
        password=QBIT_PASS,
    )


def add_magnet_to_qbit(magnet: str) -> None:
    client = _qbit_client()
    client.auth_log_in()
    client.torrents_add(urls=magnet, category=CATEGORY)


def get_qbit_torrent_hashes() -> set[str]:
    """Return set of info hashes (lowercase) for torrents currently in qBittorrent."""
    try:
        client = _qbit_client()
        client.auth_log_in()
        torrents = client.torrents_info()
        return {str(t.hash).lower() for t in torrents if getattr(t, "hash", None)}
    except Exception:
        return set()


def _hash_from_magnet(magnet: str) -> str | None:
    """Extract info hash (lowercase) from magnet link."""
    if not magnet or "btih:" not in magnet:
        return None
    try:
        ih = magnet.split("btih:")[1].split("&")[0].split("?")[0].strip()[:40]
        return ih.lower() if ih else None
    except Exception:
        return None


# --- App ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(title="Music Request", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def index():
    return FileResponse("static/index.html")


# --- API (all require auth) ---
@app.post("/api/login")
async def login(req: LoginRequest):
    ok = await verify_airsonic(req.username, req.password)
    if not ok:
        raise HTTPException(status_code=401, detail="Invalid Airsonic credentials")
    return {"ok": True, "username": req.username}


@app.get("/api/artists")
async def search_artists(q: str, _: tuple = Depends(get_auth_header)):
    if len(q.strip()) < 2:
        raise HTTPException(status_code=400, detail="Query too short")
    query = q.strip()
    try:
        artists, images = await asyncio.gather(mb_search_artists(query), deezer_artist_images(query))
        out = []
        used: dict[str, int] = {}
        for a in artists:
            name = a.get("name", "")
            norm = _norm_name(name)
            imgs = images.get(norm, [])
            idx = used.get(norm, 0)
            img = imgs[idx] if idx < len(imgs) else None
            used[norm] = idx + 1
            out.append({"id": a["id"], "name": name, "type": a.get("type", ""), "image": img})
    except (httpx.ConnectError, httpx.ConnectTimeout) as _:
        # MusicBrainz unreachable (e.g. container network); fall back to Deezer
        artists = await deezer_search_artists(query)
        out = [{"id": a["id"], "name": a["name"], "type": a.get("type", ""), "image": a.get("image")} for a in artists]
    return {"artists": out}


@app.get("/api/albums/{artist_id}")
async def get_albums(artist_id: str, _: tuple = Depends(get_auth_header)):
    if artist_id.startswith("deezer:"):
        deezer_id = artist_id[7:]
        groups = await deezer_get_albums(deezer_id)
    else:
        groups = await mb_get_release_groups(artist_id)
    def _fmt_album(g: dict) -> dict | None:
        t = g.get("primary-type") or g.get("type") or "Album"
        if t not in ("Album", "EP", "Single", None):
            return None
        date_val = (g.get("first-release-date") or g.get("date") or "")[:4]
        # Cover: Deezer has cover; MusicBrainz uses Cover Art Archive
        img = g.get("cover")
        if not img and g.get("id"):
            img = f"https://coverartarchive.org/release-group/{g['id']}/front-250"
        return {"id": g.get("id", ""), "title": g.get("title", ""), "type": t or "Album", "date": date_val, "image": img}
    albums = [a for g in groups if (a := _fmt_album(g))]
    return {"albums": albums[:100]}


@app.get("/api/search-tpb")
async def search_tpb(q: str, _: tuple = Depends(get_auth_header)):
    """Search TPB (Apibay) + Prowlarr indexers. Used for both album and discography requests."""
    if not q.strip():
        raise HTTPException(status_code=400, detail="Query required")
    try:
        results = await search_all_trackers(q.strip())
    except Exception:
        import logging
        logging.getLogger(__name__).exception("search_all_trackers failed")
        raise HTTPException(status_code=500, detail="Search failed—try again later")
    # Fetch qBittorrent hashes in thread (sync API)
    try:
        existing_hashes = await asyncio.to_thread(get_qbit_torrent_hashes)
    except Exception:
        existing_hashes = set()
    out = []
    for r in results:
        name = r.get("name", "Unknown")
        seeders = int(r.get("seeders", 0) or 0)
        leechers = int(r.get("leechers", 0) or 0)
        size = int(r.get("size", 0) or 0)
        magnet = r.get("magnet") or ""
        if not magnet:
            info_hash = r.get("info_hash") or r.get("info hash", "")
            if info_hash:
                magnet = info_hash_to_magnet(info_hash, name)
        ih = _hash_from_magnet(magnet)
        already_added = ih in existing_hashes if ih else False
        out.append({
            "name": name,
            "seeders": seeders,
            "leechers": leechers,
            "size": size,
            "added": already_added,
            "magnet": magnet,
        })
    return {"results": out}


@app.post("/api/add-to-lidarr")
async def add_to_lidarr(req: AddToLidarrRequest, _: tuple = Depends(get_auth_header)):
    """Add album to Lidarr's wanted list when no torrents found. Requires MusicBrainz album ID."""
    if not req.album_id or req.album_id.startswith("deezer:"):
        raise HTTPException(status_code=400, detail="MusicBrainz album ID required for Lidarr")
    ok = await lidarr_add_album(req.album_id)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to add album to Lidarr")
    return {"ok": True, "message": "Album added to wanted list. Lidarr will search for it and download when available."}


@app.post("/api/add-torrent")
async def add_torrent(req: AddTorrentRequest, _: tuple = Depends(get_auth_header)):
    if not req.magnet.strip().startswith("magnet:"):
        raise HTTPException(status_code=400, detail="Invalid magnet link")
    try:
        add_magnet_to_qbit(req.magnet.strip())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to add torrent: {e}")
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
