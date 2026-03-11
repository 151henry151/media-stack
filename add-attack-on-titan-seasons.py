#!/usr/bin/env python3
"""
One-off: search Apibay for Attack on Titan seasons 1–4 (English audio, smallest
well-seeded season packs), add to qBittorrent with category tv-sonarr.
Uses same logic as media-requests (English required, prefer smallest + seeders).
"""
import os
import re
import sys
import urllib.parse

import requests

try:
    import qbittorrentapi
except ImportError:
    print("qbittorrent-api required: pip install qbittorrent-api", file=sys.stderr)
    sys.exit(1)

APIBAY_BASE = "https://apibay.org"
APIBAY_CAT_TV = 199
QBIT_HOST = os.environ.get("QBIT_HOST", "localhost:5080")
QBIT_USER = os.environ.get("QBIT_USER", "admin")
QBIT_PASS = os.environ.get("QBIT_PASS", "admin123")
MIN_SEEDERS = 1
SESSION = requests.Session()
SESSION.headers["User-Agent"] = "MediaStack/1.0"


def search_apibay(query: str, cat: int = APIBAY_CAT_TV) -> list[dict]:
    try:
        r = SESSION.get(f"{APIBAY_BASE}/q.php", params={"q": query, "cat": cat}, timeout=15)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"Apibay search failed: {e}")
        return []
    if isinstance(data, dict):
        data = [data]
    return [t for t in data if t.get("id") and t["id"] != "0" and t.get("info_hash")]


def is_video_name(name: str) -> bool:
    n = (name or "").lower()
    if any(ext in n for ext in (".mkv", ".mp4", ".avi", ".m4v")):
        return True
    return any(kw in n for kw in ("1080p", "720p", "2160p", "4k", "bluray", "web-dl", "remux", "x264", "x265", "hevc"))


def has_english_audio(name: str) -> bool:
    n = (name or "").lower()
    if "english" in n or " eng " in n or " eng." in n or ".eng " in n or "[eng]" in n or "(eng)" in n:
        return True
    if "dual audio" in n or "dual.audio" in n or "dual-audio" in n:
        return True
    if "dubbed" in n or " english dub" in n or " eng dub" in n or " dub " in n:
        return True
    return False


def pick_tv(torrents: list[dict], season_num: int | None = None) -> dict | None:
    """Pick smallest well-seeded season pack. If season_num is set, only consider torrents for that season."""
    candidates = []
    if season_num == 1:
        season_markers = ["season 1", "s01", "s1 ", " 1-25", "(1)", " part 1"]
    elif season_num == 2:
        season_markers = ["season 2", "s02", "s2 "]
    elif season_num == 3:
        season_markers = ["season 3", "s03", "s3 ", "s3("]
    elif season_num == 4:
        season_markers = ["season 4", "s04", "s4 ", "final season", "the final season"]
    else:
        season_markers = []
    for t in torrents:
        size = int(t.get("size") or 0)
        if size <= 0:
            continue
        seeders = int(t.get("seeders") or 0)
        if seeders < MIN_SEEDERS:
            continue
        name = (t.get("name") or "").strip().lower()
        if not is_video_name(name) or not has_english_audio(name):
            continue
        if season_num is not None and season_markers:
            if not any(m in name for m in season_markers):
                continue
            # Exclude wrong season (e.g. for season 1, exclude "season 2", "s02")
            wrong = []
            if season_num != 1:
                wrong.extend(["season 1", "s01", " s1 "])
            if season_num != 2:
                wrong.extend(["season 2", "s02", " s2 "])
            if season_num != 3:
                wrong.extend(["season 3", "s03", " s3 "])
            if season_num != 4:
                wrong.extend(["season 4", "s04", " s4 ", "final season"])
            if any(w in name for w in wrong):
                continue
        is_full_season = "season" in name or "s01" in name or "s1 " in name or "s02" in name or "s2 " in name or "s03" in name or "s3 " in name or "s04" in name or "s4 " in name or " complete " in name or "1-25" in name or "1-12" in name or "1-10" in name
        candidates.append((size, -seeders, 0 if is_full_season else 1, t))
    if not candidates:
        return None
    candidates.sort(key=lambda x: (x[2], x[0], x[1]))
    return candidates[0][3]


def build_magnet(info_hash: str, name: str) -> str:
    info_hash = (info_hash or "").strip().upper()
    if len(info_hash) != 40 or not re.match(r"^[0-9A-Fa-f]+$", info_hash):
        return ""
    dn = urllib.parse.quote(name or "torrent", safe="")
    return f"magnet:?xt=urn:btih:{info_hash}&dn={dn}"


def add_to_qbit(magnet: str, category: str = "tv-sonarr") -> None:
    host, _, port = QBIT_HOST.partition(":")
    port = int(port) if port else 5080
    client = qbittorrentapi.Client(host=host or "localhost", port=port, username=QBIT_USER, password=QBIT_PASS)
    client.auth_log_in()
    save_path = "/downloads"
    client.torrents_add(urls=magnet, category=category, save_path=save_path, add_to_top_of_queue=True)


def main() -> None:
    # Apibay cat=199 (TV) often returns 0 for specific queries; cat=0 (all) returns more, we filter to video.
    search_cat = 0
    seasons = [
        (["Attack on Titan Season 1", "Shingeki no Kyojin Season 1", "Attack on Titan S01"], 1),
        (["Attack on Titan Season 2", "Shingeki no Kyojin Season 2", "Attack on Titan S02"], 2),
        (["Attack on Titan Season 3", "Shingeki no Kyojin Season 3", "Attack on Titan S03"], 3),
        (["Attack on Titan Season 4", "Shingeki no Kyojin Season 4", "Attack on Titan S04", "Attack on Titan Final Season"], 4),
    ]
    category = "tv-sonarr"
    added = 0
    for queries, num in seasons:
        print(f"\n--- Season {num} ---")
        torrents = []
        for query in queries:
            torrents.extend(search_apibay(query, search_cat))
        # Dedupe by info_hash
        seen = set()
        unique = []
        for t in torrents:
            h = t.get("info_hash")
            if h and h not in seen:
                seen.add(h)
                unique.append(t)
        torrents = unique
        print(f"  Apibay results: {len(torrents)}")
        chosen = pick_tv(torrents, season_num=num)
        if not chosen:
            print(f"  No suitable English-audio season pack found (need ≥{MIN_SEEDERS} seeder, video, English in name).")
            continue
        name = chosen.get("name", "?")
        size_b = int(chosen.get("size") or 0)
        seeders = int(chosen.get("seeders") or 0)
        size_gb = size_b / (1024**3)
        print(f"  Picked: {name}")
        print(f"  Size: {size_gb:.2f} GB, Seeders: {seeders}")
        magnet = build_magnet(chosen.get("info_hash", ""), chosen.get("name", ""))
        if not magnet:
            print("  Skipped: invalid magnet")
            continue
        try:
            add_to_qbit(magnet, category)
            print(f"  Added to qBittorrent with category '{category}'")
            added += 1
        except Exception as e:
            print(f"  Failed to add: {e}")
    print(f"\nDone. Added {added} torrent(s).")


if __name__ == "__main__":
    main()
