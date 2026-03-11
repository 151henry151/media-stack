#!/usr/bin/env python3
"""
Search The Pirate Bay (via apibay.org) for artist discographies and add magnet
links to qBittorrent with the lidarr category (so lidarr-torrent-import will
process them into the music library).
"""
import os
import re
import sys
import urllib.parse

import requests

try:
    import qbittorrentapi
except ImportError:
    print("Install qbittorrent-api: pip install qbittorrent-api", file=sys.stderr)
    sys.exit(1)

APIBAY = "https://apibay.org"
QBIT_HOST = os.environ.get("QBIT_HOST", "localhost:5080")
QBIT_USER = os.environ.get("QBIT_USER", "admin")
QBIT_PASS = os.environ.get("QBIT_PASS", "admin123")
CATEGORY = "lidarr"
SESSION = requests.Session()
SESSION.headers["User-Agent"] = "LidarrDiscography/1.0"


def search_apibay(query: str, cat: int = 101) -> list[dict]:
    """Search apibay for torrents. cat 101 = Audio."""
    try:
        r = SESSION.get(
            f"{APIBAY}/q.php",
            params={"q": query, "cat": cat},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"Search failed for '{query}': {e}", file=sys.stderr)
        return []

    if isinstance(data, dict):
        data = [data]
    return [t for t in data if t.get("id") and t["id"] != "0" and t.get("info_hash")]


def build_magnet(info_hash: str, name: str) -> str:
    info_hash = (info_hash or "").strip().upper()
    if len(info_hash) != 40 or not re.match(r"^[0-9A-Fa-f]+$", info_hash):
        return ""
    dn = urllib.parse.quote(name or "torrent", safe="")
    return f"magnet:?xt=urn:btih:{info_hash}&dn={dn}"


def pick_best(torrents: list[dict], artist: str) -> dict | None:
    """Pick best discography/flac torrent by seeders and name match."""
    artist_lower = artist.lower()
    scored = []
    for t in torrents:
        name = (t.get("name") or "").lower()
        seeders = int(t.get("seeders") or 0)
        # Prefer "discography", "flac", "complete"
        score = seeders
        if "discography" in name:
            score += 50
        if "flac" in name or "lossless" in name:
            score += 30
        if "complete" in name or "collection" in name:
            score += 20
        if artist_lower in name:
            score += 10
        scored.append((score, t))
    scored.sort(key=lambda x: -x[0])
    return scored[0][1] if scored and scored[0][0] > 0 else None


def main() -> int:
    artists = [
        "Eddie Jefferson",
        "Ryo Fukui",
        "Louis Armstrong",
        "Lisle Atkinson",
        "Barry White",
        "Wes Montgomery",
        "Cake",
        "White Stripes",
        "Bill Monroe",
        "Clarence White",
    ]

    if len(sys.argv) > 1:
        artists = sys.argv[1:]

    host, _, port = QBIT_HOST.partition(":")
    port = int(port) if port else 5080

    try:
        client = qbittorrentapi.Client(
            host=host or "localhost",
            port=port,
            username=QBIT_USER,
            password=QBIT_PASS,
        )
        client.auth_log_in()
    except Exception as e:
        print(f"qBittorrent login failed: {e}", file=sys.stderr)
        return 1

    existing = {t.name for t in client.torrents_info(category=CATEGORY)}
    added = 0

    for artist in artists:
        # Try discography first, then flac, then artist name. cat 101=Audio, 0=All
        for query, cat in [
            (f"{artist} discography", 101),
            (f"{artist} flac", 101),
            (artist, 101),
            (f"{artist} discography", 0),
            (artist, 0),
        ]:
            torrents = search_apibay(query, cat=cat)
            if not torrents:
                continue
            best = pick_best(torrents, artist)
            if not best:
                continue
            name = best.get("name", "")
            if name in existing:
                print(f"Skip (already added): {artist} - {name[:60]}...")
                break
            magnet = build_magnet(best.get("info_hash", ""), name)
            if not magnet:
                continue
            try:
                client.torrents_add(
                    urls=magnet,
                    category=CATEGORY,
                    tags="discographies",
                )
                print(f"Added: {artist} -> {name[:70]}{'...' if len(name) > 70 else ''}")
                existing.add(name)
                added += 1
            except Exception as e:
                print(f"Add failed for {artist}: {e}", file=sys.stderr)
            break
        else:
            print(f"No results: {artist}")

    print(f"\nAdded {added} torrent(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
