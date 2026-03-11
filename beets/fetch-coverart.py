#!/usr/bin/env python3
"""
Fetch album art from Cover Art Archive (MusicBrainz) for beets albums that lack it.
Uses archive.org URL format (CAA API now redirects to this).
Writes cover.jpg to album folder and optionally embeds via beets.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import requests
from beets.library import Library

CONFIG = os.environ.get("BEETS_CONFIG", "/home/henry/.config/beets/config.yaml")
LIBRARY = os.environ.get("BEETS_LIBRARY", "/home/henry/.config/beets/musiclibrary.db")
COVER_NAMES = ("cover.jpg", "cover.png", "front.jpg", "folder.jpg")
SESSION = requests.Session()
SESSION.headers["User-Agent"] = "BeetsCoverArtFetcher/1.0 (https://beets.io)"


def album_has_cover(album_path: Path) -> bool:
    """Check if album folder already has a cover image."""
    if not album_path or not album_path.exists():
        return False
    for name in COVER_NAMES:
        if (album_path / name).exists():
            return True
    return False


# Cover Art Archive requires MusicBrainz UUID format (e.g. d722910c-42a6-4328-b9b8-df5b89361971)
MBID_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


def lookup_mbid(artist: str, album: str, album_only: bool = False) -> str | None:
    """Search MusicBrainz for release UUID by artist and album."""
    if not album:
        return None
    queries = []
    if artist and not album_only:
        queries.append(f'artist:"{artist}" AND release:"{album}"')
    # Fallback: search by album only (helps compilations, VA)
    queries.append(f'release:"{album}"')
    for query in queries:
        try:
            r = SESSION.get(
                "https://musicbrainz.org/ws/2/release/",
                params={"query": query, "fmt": "json", "limit": 5},
                timeout=10,
            )
            r.raise_for_status()
            data = r.json()
            releases = data.get("releases", [])
            for rel in releases:
                # Prefer releases that have cover art in CAA
                rid = rel.get("id")
                if rid and MBID_UUID_RE.match(rid):
                    return rid
            if releases:
                return releases[0].get("id")
        except Exception:
            continue
    return None


def fetch_from_caa(mbid: str) -> bytes | None:
    """Fetch front cover from Cover Art Archive via archive.org."""
    if not mbid or not MBID_UUID_RE.match(str(mbid).strip()):
        return None
    url = f"https://archive.org/download/mbid-{mbid}/index.json"
    try:
        r = SESSION.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
    except Exception:
        return None
    images = data.get("images", [])
    front = next((i for i in images if i.get("front") and "Front" in i.get("types", [])), None)
    if not front:
        return None
    img_url = front.get("image") or front.get("thumbnails", {}).get("500")
    if not img_url:
        return None
    try:
        r = SESSION.get(img_url, timeout=15)
        r.raise_for_status()
        return r.content
    except Exception:
        return None


def fetch_from_itunes(artist: str, album: str) -> bytes | None:
    """Fallback: fetch album art from iTunes Search API."""
    album_lower = (album or "").lower()
    if not album_lower:
        return None
    # Try artist+album first, then album only
    for term in [f"{artist} {album}".strip(), album]:
        if not term:
            continue
        try:
            r = SESSION.get(
                "https://itunes.apple.com/search",
                params={"term": term, "media": "music", "entity": "album", "limit": 10},
                timeout=10,
            )
            r.raise_for_status()
            data = r.json()
            results = data.get("results", [])
            for res in results:
                coll = (res.get("collectionName") or "").lower()
                # Prefer results where album name appears in collection name
                if album_lower not in coll and not coll.startswith(album_lower[:20]):
                    continue
                art_url = res.get("artworkUrl100", "").replace("100x100", "600x600")
                if not art_url:
                    continue
                try:
                    r2 = SESSION.get(art_url, timeout=10)
                    r2.raise_for_status()
                    return r2.content
                except Exception:
                    continue
            # If no close match, use first result for short queries
            if len(album) >= 15 and results:
                art_url = results[0].get("artworkUrl100", "").replace("100x100", "600x600")
                if art_url:
                    try:
                        r2 = SESSION.get(art_url, timeout=10)
                        r2.raise_for_status()
                        return r2.content
                    except Exception:
                        pass
        except Exception:
            continue
    return None


def main() -> int:
    lib = Library(LIBRARY)
    count = 0
    for album in lib.albums():
        if not album.items():
            continue
        path_val = album.path
        album_path = Path(path_val.decode() if isinstance(path_val, bytes) else path_val)
        if not album_path.exists():
            continue  # Skip stale entries (e.g. lidarr staging that was cleaned)
        if album_has_cover(album_path):
            continue
        mbid = str(album.mb_albumid or "").strip()
        if not mbid or not MBID_UUID_RE.match(mbid):
            # No valid mbid: search MusicBrainz by artist+album, then album only
            mbid = lookup_mbid(
                str(album.albumartist or ""), str(album.album or ""), album_only=False
            )
        data = fetch_from_caa(mbid) if mbid else None
        if not data:
            # Fallback: iTunes Search (often has art for compilations/older releases)
            data = fetch_from_itunes(
                str(album.albumartist or ""), str(album.album or "")
            )
        if not data:
            continue
        ext = "jpg" if data[:3] == b"\xff\xd8\xff" else "png"
        cover_path = album_path / f"cover.{ext}"
        try:
            cover_path.write_bytes(data)
            album.set_art(str(cover_path))
            album.store()
            print(f"Fetched: {album.albumartist} - {album.album}")
            count += 1
        except OSError as e:
            print(f"Write failed {album}: {e}", file=sys.stderr)
    print(f"Fetched art for {count} albums")
    return 0


if __name__ == "__main__":
    sys.exit(main())
