#!/usr/bin/env python3
"""
Import completed qBittorrent torrents (category: lidarr) into the music library.
- Only processes torrents that are 100% complete
- Copies files to music/_Import/, runs beets to tag/organize, then triggers Airsonic scan
- Tags processed torrents as 'beets_imported' to avoid re-processing
"""
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

try:
    import qbittorrentapi
except ImportError:
    print("Install qbittorrent-api: pip install qbittorrent-api", file=sys.stderr)
    sys.exit(1)

# Config - override with env vars
QBIT_HOST = os.environ.get("QBIT_HOST", "localhost:5080")
QBIT_USER = os.environ.get("QBIT_USER", "admin")
QBIT_PASS = os.environ.get("QBIT_PASS", "adminadmin")
MUSIC_DIR = Path(os.environ.get("MUSIC_DIR", "/mnt/media-storage/music"))
DOWNLOADS_DIR = Path(os.environ.get("DOWNLOADS_DIR", "/mnt/media-storage/downloads"))
# Staging outside library so beets import -m actually moves (not copies)
IMPORT_DIR = Path(os.environ.get("LIDARR_IMPORT_DIR", "/mnt/media-storage/.lidarr-import-staging"))
BEETS_CMD = os.environ.get("BEETS_CMD", "/home/henry/beets-venv/bin/beet")
BEETS_CONFIG = os.environ.get("BEETS_CONFIG", "/home/henry/.config/beets/config.yaml")
PROCESSED_TAG = "beets_imported"
CATEGORY = "lidarr"
AUDIO_EXTENSIONS = {".flac", ".mp3", ".m4a", ".ogg", ".wav", ".aac", ".opus", ".alac"}


def sanitize_name(name: str) -> str:
    """Make a safe directory name from torrent name."""
    # Remove or replace problematic chars
    s = re.sub(r'[<>:"/\\|?*]', "_", name)
    s = re.sub(r'\s+', " ", s).strip()
    return s[:200] if s else "unnamed"


def has_audio_files(path: Path) -> bool:
    """Check if directory contains audio files."""
    for f in path.rglob("*"):
        if f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS:
            return True
    return False


def collect_audio_paths(path: Path) -> list[Path]:
    """Get all audio files (and their parent dirs for structure) under path."""
    files = []
    for f in path.rglob("*"):
        if f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS:
            files.append(f)
    return files


def copy_or_hardlink(src: Path, dest: Path, same_fs: bool) -> None:
    """Copy file, using hardlink if same filesystem to save space."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if same_fs:
        try:
            os.link(src, dest)
            return
        except OSError:
            pass
    shutil.copy2(src, dest)


def main() -> int:
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

    import_dir = IMPORT_DIR
    import_dir.mkdir(parents=True, exist_ok=True)
    try:
        src_stat = os.stat(DOWNLOADS_DIR)
        dst_stat = os.stat(MUSIC_DIR)
        same_fs = src_stat.st_dev == dst_stat.st_dev
    except OSError:
        same_fs = False

    processed = 0
    for t in client.torrents_info(category=CATEGORY):
        if PROCESSED_TAG in (t.tags or "").split(","):
            continue
        if t.progress < 1.0:
            continue

        name = t.name
        # qBittorrent returns container paths; map to host path
        # Container: /downloads or /media/downloads -> host DOWNLOADS_DIR
        def to_host_path(p: str) -> Path:
            s = str(p)
            for prefix in ("/media/downloads", "\\media\\downloads", "/downloads", "\\downloads"):
                if s.startswith(prefix):
                    rest = s[len(prefix):].lstrip("/\\")
                    return (Path(DOWNLOADS_DIR) / rest).resolve() if rest else Path(DOWNLOADS_DIR).resolve()
            return Path(s).resolve()

        content_path = to_host_path(t.content_path) if t.content_path else None
        if not content_path or not content_path.exists():
            save_path = to_host_path(t.save_path)
            content_path = (save_path / t.name).resolve()
        if not content_path.exists():
            print(f"Skipping {t.name}: path not found {content_path}", file=sys.stderr)
            continue
        if not has_audio_files(content_path):
            print(f"Skipping {name}: no audio files found", file=sys.stderr)
            continue

        dest_subdir = import_dir / sanitize_name(name)
        if dest_subdir.exists():
            shutil.rmtree(dest_subdir)
        dest_subdir.mkdir(parents=True)

        audio_files = collect_audio_paths(content_path)
        for src_file in audio_files:
            rel = src_file.relative_to(content_path)
            dest_file = dest_subdir / rel
            copy_or_hardlink(src_file, dest_file, same_fs)

        # Run beets import with -m to move into library structure
        result = subprocess.run(
            [BEETS_CMD, "-c", BEETS_CONFIG, "import", "-q", "-m", str(dest_subdir)],
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode != 0:
            print(f"Beets import failed for {name}: {result.stderr}", file=sys.stderr)
            continue

        # Always remove staging dir after successful import to avoid duplicates.
        # Beets may copy rather than move when source is inside library, leaving
        # duplicate files in _Import.
        if dest_subdir.exists():
            try:
                shutil.rmtree(dest_subdir)
            except OSError as e:
                print(f"Could not remove staging dir {dest_subdir}: {e}", file=sys.stderr)

        try:
            client.torrents_add_tags([t.hash], PROCESSED_TAG)
        except Exception as e:
            print(f"Could not tag torrent {name}: {e}", file=sys.stderr)

        processed += 1
        print(f"Imported: {name}")

    if processed > 0:
        # Signal that full beets import (fetchart, embedart, etc.) should run
        flag_path = os.environ.get("BEETS_IMPORT_PENDING", "/var/run/beets-import-pending")
        try:
            Path(flag_path).touch()
        except OSError:
            pass

        # Trigger Airsonic rescan (Subsonic API)
        airsonic_url = os.environ.get("AIRSONIC_URL", "http://localhost:4040")
        airsonic_user = os.environ.get("AIRSONIC_USER", "admin")
        airsonic_pass = os.environ.get("AIRSONIC_PASS", "")
        if airsonic_pass:
            import hashlib
            import urllib.request
            salt = os.urandom(8).hex()
            token = hashlib.md5((airsonic_pass + salt).encode()).hexdigest()
            try:
                url = f"{airsonic_url.rstrip('/')}/rest/startScan?u={airsonic_user}&t={token}&s={salt}&v=1.15.0&c=lidarr-import"
                urllib.request.urlopen(url, timeout=10)
            except Exception as e:
                print(f"Airsonic scan trigger failed (optional): {e}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
