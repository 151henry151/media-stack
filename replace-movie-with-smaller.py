#!/usr/bin/env python3
"""
Replace a high-disk-usage movie with a much smaller version from The Pirate Bay.

1. Picks the largest movie file in the movies library (like compress-media-nightly).
2. Searches Apibay (TPB) for a smaller release of the same movie.
3. Adds the chosen torrent to qBittorrent and waits for completion.
4. With category "radarr" (default): deletes the old library file after the download completes; Radarr
   imports the new file from the download folder to /mnt/media-storage/movies. Without radarr:
   moves the new file into the library and optionally removes the torrent.

Usage:
  ./replace-movie-with-smaller.py              # run full flow (pick, search, download, replace)
  ./replace-movie-with-smaller.py --dry-run    # only print what would be done
  ./replace-movie-with-smaller.py --add-only   # add torrent and exit (no wait/replace)

Env: MEDIA_BASE, MOVIES_DIR, DOWNLOADS_DIR, MIN_SIZE_GB, MIN_SIZE_SAVINGS_GB, MIN_SEEDERS,
QBIT_HOST, QBIT_USER, QBIT_PASS, REPLACE_MOVIE_QBIT_CATEGORY (default radarr).
For Radarr with Docker qBittorrent: save path defaults to /downloads so Radarr finds the completed
download. Override with QBIT_SAVE_PATH_REPLACEMENT if needed (e.g. /downloads).
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import time
import urllib.parse
from pathlib import Path

import requests

try:
    import qbittorrentapi
except ImportError:
    print("Install qbittorrent-api: pip install qbittorrent-api", file=sys.stderr)
    sys.exit(1)

# --- Config (override with env) ---
MEDIA_BASE = os.environ.get("MEDIA_BASE", "/mnt/media-storage")
MOVIES_DIR = Path(os.environ.get("MOVIES_DIR", str(Path(MEDIA_BASE) / "movies")))
DOWNLOADS_DIR = Path(os.environ.get("DOWNLOADS_DIR", str(Path(MEDIA_BASE) / "downloads")))
REPLACEMENT_SUBDIR = os.environ.get("REPLACEMENT_SUBDIR", "replacement-movies")
MIN_SIZE_GB = float(os.environ.get("MIN_SIZE_GB", "3"))
# New release must be at least this many GB smaller than current (default 2 GB).
MIN_SIZE_SAVINGS_GB = float(os.environ.get("MIN_SIZE_SAVINGS_GB", "2"))
MIN_SEEDERS = int(os.environ.get("MIN_SEEDERS", "1"))  # at least 1 seeder
# Prefer candidates with at least this many seeders when available (reduces "stuck on metadata").
PREFER_SEEDERS = int(os.environ.get("PREFER_SEEDERS", "5"))
# Prefer replacement files under this size (GB) when available; requirement is still MIN_SIZE_SAVINGS_GB smaller.
PREFER_MAX_SIZE_GB = float(os.environ.get("PREFER_MAX_SIZE_GB", "5"))
APIBAY_BASE = "https://apibay.org"
APIBAY_CAT_MOVIES = 207  # Video > HD - Movies
QBIT_HOST = os.environ.get("QBIT_HOST", "localhost:5080")
QBIT_USER = os.environ.get("QBIT_USER", "admin")
QBIT_PASS = os.environ.get("QBIT_PASS", "admin123")
# Path as seen by qBittorrent when adding. For Radarr: use /downloads (Docker) so Radarr finds completed downloads.
QBIT_SAVE_PATH_REPLACEMENT = os.environ.get("QBIT_SAVE_PATH_REPLACEMENT", "")
# Category for new torrents. Use "radarr" so Radarr imports and moves to /mnt/media-storage/movies.
CATEGORY = os.environ.get("REPLACE_MOVIE_QBIT_CATEGORY", "radarr")
VIDEO_EXTENSIONS = {".mkv", ".mp4", ".avi", ".m4v", ".mov"}
POLL_INTERVAL = 60
POLL_TIMEOUT_HOURS = 24
# Shared with compress-media-nightly: paths in this file are "in use" and must not be picked by the other script.
CLAIMED_FILE = Path(os.environ.get("MEDIA_STACK_CLAIMED_FILE", "/var/run/media-stack-claimed.txt"))
# Replace skips if compress is running (same lock as compress-media-nightly).
COMPRESS_LOCK_FILE = os.environ.get("COMPRESS_LOCK_FILE", "/var/run/compress-media-nightly.lock")
SESSION = requests.Session()
SESSION.headers["User-Agent"] = "ReplaceMovieWithSmaller/1.0"


def log(msg: str) -> None:
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def read_claimed_paths() -> set[str]:
    """Return set of paths currently claimed by compress or replace (one path per line)."""
    if not CLAIMED_FILE.exists():
        return set()
    try:
        lines = CLAIMED_FILE.read_text().strip().splitlines()
        return {p.strip() for p in lines if p.strip()}
    except OSError:
        return set()


def add_claimed_path(path: Path) -> None:
    """Append path to the shared claim file so compress-nightly won't pick it."""
    try:
        with open(CLAIMED_FILE, "a") as f:
            f.write(str(path.resolve()) + "\n")
    except OSError as e:
        log(f"Warning: could not add to claim file: {e}")


def remove_claimed_path(path: Path) -> None:
    """Remove path from the shared claim file."""
    if not CLAIMED_FILE.exists():
        return
    try:
        target = str(path.resolve())
        lines = [p for p in CLAIMED_FILE.read_text().splitlines() if p.strip() != target]
        CLAIMED_FILE.write_text("\n".join(lines) + ("\n" if lines else ""))
    except OSError as e:
        log(f"Warning: could not remove from claim file: {e}")


def compress_lock_held() -> bool:
    """Return True if compress-media-nightly is running (holds the lock)."""
    try:
        import fcntl
        with open(COMPRESS_LOCK_FILE, "a") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        return False
    except (OSError, FileNotFoundError):
        return True


def find_largest_movie(min_gb: float, exclude_paths: set[str] | None = None) -> tuple[int, Path] | None:
    """Return (size_bytes, path) for the largest movie file >= min_gb, or None. Excludes paths in exclude_paths."""
    min_bytes = int(min_gb * 1024**3)
    excluded = exclude_paths or set()
    if not MOVIES_DIR.is_dir():
        log(f"Movies dir not found: {MOVIES_DIR}")
        return None
    best_size = 0
    best_path: Path | None = None
    for ext in VIDEO_EXTENSIONS:
        for f in MOVIES_DIR.rglob(f"*{ext}"):
            if not f.is_file():
                continue
            if ".compress-backup" in f.parts or ".compress-temp" in f.parts:
                continue
            if str(f.resolve()) in excluded:
                continue
            try:
                size = f.stat().st_size
            except OSError:
                continue
            if size >= min_bytes and size > best_size:
                best_size = size
                best_path = f
    if best_path is None:
        return None
    return (best_size, best_path)


def parse_movie_query(movie_path: Path) -> str:
    """Build search query from movie path. Uses parent dir name, e.g. 'Incredibles 2 (2018)' -> 'Incredibles 2 2018'."""
    parent = movie_path.parent.name
    # "Movie Name (Year)" or "Movie Name (Year) [Extra]" -> "Movie Name Year"
    m = re.match(r"^(.+?)\s*\((\d{4})\)", parent, re.IGNORECASE)
    if m:
        return f"{m.group(1).strip()} {m.group(2)}"
    return parent.replace(".", " ").strip()


def search_apibay(query: str, cat: int = APIBAY_CAT_MOVIES) -> list[dict]:
    """Search Apibay for torrents. Returns list of dicts with id, name, info_hash, size, seeders, leechers."""
    try:
        r = SESSION.get(
            f"{APIBAY_BASE}/q.php",
            params={"q": query, "cat": cat},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        log(f"Apibay search failed for '{query}': {e}")
        return []
    if isinstance(data, dict):
        data = [data]
    return [
        t
        for t in data
        if t.get("id") and t["id"] != "0" and t.get("info_hash")
    ]


def build_magnet(info_hash: str, name: str) -> str:
    info_hash = (info_hash or "").strip().upper()
    if len(info_hash) != 40 or not re.match(r"^[0-9A-Fa-f]+$", info_hash):
        return ""
    dn = urllib.parse.quote(name or "torrent", safe="")
    return f"magnet:?xt=urn:btih:{info_hash}&dn={dn}"


def is_video_name(name: str) -> bool:
    n = (name or "").lower()
    if any(n.endswith(ext) for ext in VIDEO_EXTENSIONS) or any(ext in n for ext in (".mkv", ".mp4", ".avi", ".m4v")):
        return True
    # Torrent names often omit extension but include quality/format (e.g. "1080p BluRay HEVC")
    return any(kw in n for kw in ("1080p", "720p", "2160p", "4k", "bluray", "web-dl", "webdl", "remux", "x264", "x265", "hevc", "h.264"))


def pick_smaller_torrent(
    torrents: list[dict],
    current_size: int,
    min_savings_gb: float = MIN_SIZE_SAVINGS_GB,
    min_seeders: int = MIN_SEEDERS,
    prefer_max_size_gb: float = PREFER_MAX_SIZE_GB,
) -> dict | None:
    """Pick a torrent that is at least min_savings_gb smaller than current_size, has min_seeders, and looks like a movie."""
    min_savings_bytes = int(min_savings_gb * 1024**3)
    max_size = current_size - min_savings_bytes
    prefer_max_bytes = int(prefer_max_size_gb * 1024**3)
    candidates = []
    for t in torrents:
        size = int(t.get("size") or 0)
        if size <= 0 or size >= max_size:
            continue
        seeders = int(t.get("seeders") or 0)
        if seeders < min_seeders:
            continue
        name = (t.get("name") or "").strip()
        if not is_video_name(name):
            continue
        # Prefer 720p / x264 / smaller encodes (often in name)
        score = seeders
        if "720" in name or "720p" in name.lower():
            score += 30
        if "x264" in name.lower() or "h.264" in name.lower():
            score += 20
        if "1080" not in name and "2160" not in name and "4k" not in name.lower():
            score += 10
        candidates.append((score, seeders, size, -size, t))
    if not candidates:
        return None
    # Prefer candidates with PREFER_SEEDERS or more when available (fewer "stuck on metadata")
    strong = [c for c in candidates if c[1] >= PREFER_SEEDERS]
    pool = strong if strong else candidates
    # Prefer candidates under PREFER_MAX_SIZE_GB when available
    small = [c for c in pool if c[2] < prefer_max_bytes]
    pool = small if small else pool
    pool.sort(key=lambda x: (x[0], x[3]), reverse=True)
    return pool[0][4]


def get_qbit_client() -> qbittorrentapi.Client:
    host, _, port = QBIT_HOST.partition(":")
    port = int(port) if port else 5080
    client = qbittorrentapi.Client(
        host=host or "localhost",
        port=port,
        username=QBIT_USER,
        password=QBIT_PASS,
    )
    client.auth_log_in()
    return client


def to_host_path(p: str) -> Path:
    """Map qBittorrent container path to host path (downloads)."""
    s = str(p or "")
    for prefix in ("/media/downloads", "\\media\\downloads", "/downloads", "\\downloads"):
        if s.startswith(prefix):
            rest = s[len(prefix) :].lstrip("/\\")
            return (DOWNLOADS_DIR / rest).resolve() if rest else DOWNLOADS_DIR.resolve()
    return Path(s).resolve()


def find_main_video(content_path: Path) -> Path | None:
    """Return the largest video file under content_path (file or directory)."""
    if content_path.is_file() and content_path.suffix.lower() in VIDEO_EXTENSIONS:
        return content_path
    best: Path | None = None
    best_size = 0
    for ext in VIDEO_EXTENSIONS:
        for f in content_path.rglob(f"*{ext}"):
            if not f.is_file():
                continue
            try:
                size = f.stat().st_size
            except OSError:
                continue
            if size > best_size:
                best_size = size
                best = f
    return best


def wait_for_completion(
    client: qbittorrentapi.Client,
    info_hash: str,
    poll_interval: int = POLL_INTERVAL,
    timeout_hours: float = POLL_TIMEOUT_HOURS,
) -> bool:
    """Poll until torrent is 100% complete or timeout. Returns True if completed."""
    deadline = time.monotonic() + timeout_hours * 3600
    while time.monotonic() < deadline:
        for t in client.torrents_info():
            if (t.hash or "").upper() == (info_hash or "").upper():
                if t.progress >= 1.0:
                    return True
                log(f"  Progress {t.progress * 100:.0f}%")
                break
        time.sleep(poll_interval)
    return False


def verify_video(path: Path) -> bool:
    """Quick ffprobe check that the file is a valid video."""
    import subprocess
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if r.returncode != 0:
        return False
    try:
        float(r.stdout.strip())
        return True
    except (ValueError, TypeError):
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Replace a large movie with a smaller TPB release.")
    parser.add_argument("--dry-run", action="store_true", help="Only print what would be done")
    parser.add_argument("--add-only", action="store_true", help="Add torrent and exit (do not wait or replace)")
    parser.add_argument("--min-size-gb", type=float, default=MIN_SIZE_GB, help=f"Min movie size in GB (default {MIN_SIZE_GB})")
    parser.add_argument("--movie-path", type=str, default="", help="Use this movie file instead of scanning for largest (skips slow scan)")
    parser.add_argument("--remove-torrent-after", action="store_true", help="Remove the torrent (and its data) from qBittorrent after successful replacement")
    parser.add_argument("--batch", type=int, default=0, metavar="N", help="Add torrents for N next-biggest movies (implies --add-only); paths stay claimed")
    args = parser.parse_args()
    dry_run = args.dry_run
    add_only = args.add_only
    min_size_gb = args.min_size_gb
    movie_path_arg = (args.movie_path or "").strip()
    remove_torrent_after = args.remove_torrent_after
    batch_count = max(0, args.batch)
    if batch_count > 0:
        add_only = True

    log("=== replace-movie-with-smaller ===")

    # Avoid colliding with compress-media-nightly: skip if it is running.
    if compress_lock_held():
        log("compress-media-nightly is running (lock held); exiting to avoid collision.")
        return 0

    batch_mode = batch_count > 0
    added = 0
    for _ in range(batch_count) if batch_mode else [0]:
        claimed = read_claimed_paths()

        # 1. Pick largest movie (or use --movie-path; only when not in batch)
        if movie_path_arg and not batch_mode:
            movie_path = Path(movie_path_arg).resolve()
            if not movie_path.is_file():
                log(f"File not found: {movie_path}")
                break
            if str(movie_path) in claimed:
                log("Requested movie path is claimed by another run; skipping.")
                break
            current_size = movie_path.stat().st_size
            if current_size < int(min_size_gb * 1024**3):
                log(f"File smaller than --min-size-gb ({min_size_gb} GB); use a larger file or lower --min-size-gb")
                break
            result = (current_size, movie_path)
        else:
            result = find_largest_movie(min_size_gb, exclude_paths=claimed)
        if not result:
            log(f"No movie >= {min_size_gb} GB found in {MOVIES_DIR}")
            break
        current_size, movie_path = result
        size_gb = current_size / (1024**3)
        log(f"Largest movie: {movie_path} ({size_gb:.1f} GB)")

        query = parse_movie_query(movie_path)
        log(f"Search query: {query}")

        # 2. Search Apibay (fallback: try without year if no results)
        torrents = search_apibay(query)
        if not torrents and re.search(r"\s\d{4}$", query.strip()):
            fallback_query = re.sub(r"\s+\d{4}$", "", query.strip())
            log(f"No results; trying without year: {fallback_query}")
            torrents = search_apibay(fallback_query)
        if not torrents:
            log("No Apibay results.")
            break
        log(f"Found {len(torrents)} torrent(s)")

        chosen = pick_smaller_torrent(torrents, current_size)
        if not chosen:
            log("No smaller, well-seeded movie release found.")
            break

        name = chosen.get("name", "Unknown")
        size_bytes = int(chosen.get("size") or 0)
        seeders = int(chosen.get("seeders") or 0)
        info_hash = (chosen.get("info_hash") or "").strip().upper()
        log(f"Chosen: {name} ({size_bytes / (1024**3):.2f} GB, {seeders} seeders)")

        if dry_run:
            log("Dry run: would add this torrent, wait for completion, then replace and delete old file.")
            if remove_torrent_after:
                log("Dry run: would remove torrent from qBittorrent after replacement.")
            break

        add_claimed_path(movie_path)
        try:
            magnet = build_magnet(info_hash, name)
            if not magnet:
                log("Invalid info_hash; cannot build magnet.")
                break

            # 3. Add to qBittorrent (category "radarr" so Radarr will import to movies when done)
            if QBIT_SAVE_PATH_REPLACEMENT.strip():
                save_path_for_add = QBIT_SAVE_PATH_REPLACEMENT.strip()
            elif CATEGORY == "radarr":
                save_path_for_add = "/downloads"
            else:
                save_path_for_add = str(DOWNLOADS_DIR / REPLACEMENT_SUBDIR)
                Path(save_path_for_add).mkdir(parents=True, exist_ok=True)
            add_kw = {"urls": magnet, "category": CATEGORY, "add_to_top_of_queue": True}
            if save_path_for_add:
                add_kw["save_path"] = save_path_for_add
            try:
                client = get_qbit_client()
                client.torrents_add(**add_kw)
                log(f"Added torrent to qBittorrent (category={CATEGORY}, save_path={save_path_for_add or 'default'})")
            except Exception as e:
                log(f"qBittorrent add failed: {e}")
                break
            added += 1

            if add_only:
                log("Add-only: exiting." if not batch_mode else "Queued for replacement.")
                if batch_mode:
                    continue
                break

            # 4. Wait for completion
            log("Waiting for download to complete (polling)...")
            if not wait_for_completion(client, info_hash):
                log("Timeout waiting for completion. Exiting; you can move the file manually when done.")
                break

            if CATEGORY == "radarr":
                log(f"Deleting old library file to free space: {movie_path}")
                movie_path.unlink(missing_ok=True)
                log("Done. Radarr will import the new file to /mnt/media-storage/movies.")
                break

            # 5. Locate new file (non-Radarr)
            torrent = None
            for t in client.torrents_info():
                if (t.hash or "").upper() == info_hash:
                    torrent = t
                    break
            if not torrent:
                log("Torrent not found after completion.")
                break
            content_path = to_host_path(torrent.content_path) if torrent.content_path else None
            if not content_path or not content_path.exists():
                save_path_host = to_host_path(torrent.save_path) if torrent.save_path else (DOWNLOADS_DIR / REPLACEMENT_SUBDIR)
                content_path = (Path(save_path_host) / torrent.name).resolve()
            if not content_path.exists():
                log(f"Content path not found: {content_path}")
                break

            new_file = find_main_video(content_path)
            if not new_file or not new_file.is_file():
                log("No video file found in downloaded content.")
                break

            if not verify_video(new_file):
                log("New file failed ffprobe verification; aborting replace.")
                break

            old_file = movie_path
            dest_file = old_file.parent / (old_file.stem + new_file.suffix)
            if dest_file.resolve() == new_file.resolve():
                log("New file already at destination.")
            else:
                if dest_file.exists():
                    dest_file.unlink()
                log(f"Moving {new_file} -> {dest_file}")
                shutil.move(str(new_file), str(dest_file))
                log(f"Removing old file: {old_file}")
                old_file.unlink(missing_ok=True)
                log("Replacement done.")

            if remove_torrent_after:
                try:
                    client.torrents_delete(delete_files=True, torrent_hashes=[torrent.hash])
                    log("Removed torrent from qBittorrent (and deleted its data).")
                except Exception as e:
                    log(f"Warning: could not remove torrent from qBittorrent: {e}")
            break
        finally:
            if not batch_mode:
                remove_claimed_path(movie_path)

    if batch_mode:
        log(f"Added {added} torrent(s) for replacement.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
