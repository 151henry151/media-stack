#!/usr/bin/env python3
"""
Remove qBittorrent torrents that are in 'error' or 'missingFiles' state.
Deletes the torrent from the client AND deletes their data (to free pre-allocated space).
Keeps pre-allocate setting useful for in-progress downloads while freeing space from bad torrents.

Usage:
  ./qbit-remove-errored-torrents.py           # actually delete
  ./qbit-remove-errored-torrents.py --dry-run # only list what would be removed

Env (defaults): QBIT_HOST=localhost:5080, QBIT_USER=admin, QBIT_PASS=admin123
"""
import os
import sys

try:
    import qbittorrentapi
except ImportError:
    print("Install qbittorrent-api: pip install qbittorrent-api", file=sys.stderr)
    sys.exit(1)

QBIT_HOST = os.environ.get("QBIT_HOST", "localhost:5080")
QBIT_USER = os.environ.get("QBIT_USER", "admin")
QBIT_PASS = os.environ.get("QBIT_PASS", "admin123")

# States that indicate broken/missing data we want to remove (and free space)
REMOVE_STATES = ("error", "missingfiles")


def main():
    dry_run = "--dry-run" in sys.argv
    if dry_run:
        print("DRY RUN – no torrents or files will be deleted\n")

    host, _, port = QBIT_HOST.rpartition(":")
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

    # Get all torrents and filter by state (API status_filter='errored' may not include missingFiles)
    all_torrents = client.torrents_info()
    to_remove = [t for t in all_torrents if (getattr(t, "state", None) or "").lower() in REMOVE_STATES]

    if not to_remove:
        print("No errored or missing-files torrents found.")
        return 0

    total_size = sum(t.size or 0 for t in to_remove)
    size_gb = total_size / (1024**3)
    print(f"Found {len(to_remove)} torrent(s) in error/missingFiles state (~{size_gb:.1f} GB):")
    for t in to_remove:
        name = getattr(t, "name", t.hash) or t.hash
        size_mb = (t.size or 0) / (1024**2)
        print(f"  - {name} (state={t.state}, ~{size_mb:.0f} MB)")
    print()

    if dry_run:
        print("Dry run: would delete these torrents and their data.")
        return 0

    hashes = [t.hash for t in to_remove]
    try:
        client.torrents_delete(delete_files=True, torrent_hashes=hashes)
        print(f"Removed {len(hashes)} torrent(s) and their data.")
    except Exception as e:
        print(f"Delete failed: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
