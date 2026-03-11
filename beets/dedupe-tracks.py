#!/usr/bin/env python3
"""
Remove duplicate tracks from the music library.
When the same track exists in multiple formats/locations (e.g. flac + mp3),
keeps the best quality and removes the rest.

Quality order: flac > m4a > alac > ogg > mp3 > wav (wav is often uncompressed, keep flac over wav for metadata)

Run with --dry-run to preview. Run as root (music dir may have restricted permissions).
"""
import os
import sys
from collections import defaultdict
from pathlib import Path

# Format quality (higher = prefer to keep)
FMT_RANK = {
    "flac": 10,
    "m4a": 8,
    "alac": 9,
    "ogg": 6,
    "opus": 7,
    "mp3": 4,
    "wav": 3,  # Often redundant with flac, flac has metadata
    "aac": 5,
}

sys.path.insert(0, "/home/henry/beets-venv/lib/python3.11/site-packages")
from beets.library import Library
from beets.util import syspath


def format_rank(path: str) -> int:
    ext = Path(path).suffix.lower().lstrip(".")
    return FMT_RANK.get(ext, 0)


def main():
    dry_run = "--dry-run" in sys.argv
    skip_backup = "--no-backup" in sys.argv
    if dry_run:
        print("DRY RUN - no files will be deleted\n")

    lib = Library("/home/henry/.config/beets/musiclibrary.db")

    # Group by (artist, album, track, title) - normalized for matching
    def norm(s):
        return (s or "").strip().lower()[:80]

    by_track = defaultdict(list)
    for item in lib.items():
        path = syspath(item.path)
        if not os.path.exists(path):
            continue
        artist, album, title = norm(item.artist), norm(item.album), norm(item.title)
        track = int(item.track or 0)
        # Require meaningful metadata - don't group unknowns (e.g. chrismas Track X.wav)
        if not artist and not album:
            continue
        if not title and not Path(path).stem.replace(" ", ""):
            continue
        key = (artist, album, track, title)
        by_track[key].append((item, path))

    to_remove = []
    for key, items in by_track.items():
        if len(items) < 2:
            continue
        # Sort by format quality (desc), then path length (shorter often = canonical)
        items_sorted = sorted(
            items,
            key=lambda x: (-format_rank(x[1]), len(x[1])),
        )
        keep = items_sorted[0]
        for item, path in items_sorted[1:]:
            to_remove.append((item, path, keep[1]))

    if not to_remove:
        print("No duplicate tracks found.")
        return 0

    print(f"Found {len(to_remove)} duplicate track(s) to remove:\n")
    for item, path, keep_path in to_remove[:15]:
        ext = Path(path).suffix
        keep_ext = Path(keep_path).suffix
        print(f"  Remove {ext}: {Path(path).name}")
        print(f"    Keep {keep_ext}: {Path(keep_path).name}")
    if len(to_remove) > 15:
        print(f"  ... and {len(to_remove) - 15} more")

    if not dry_run and to_remove:
        import shutil
        backup_dir = Path("/mnt/media-storage/.dedupe-backup")
        if not skip_backup:
            backup_dir.mkdir(parents=True, exist_ok=True)
            print(f"\nBacking up {len(to_remove)} duplicates to {backup_dir}...")
            for item, path, _ in to_remove:
                try:
                    rel = path.replace("/mnt/media-storage/music/", "").replace("/", "_")
                    dest = backup_dir / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, dest)
                except OSError as e:
                    print(f"  Backup failed {path}: {e}", file=sys.stderr)
        print(f"Removing {len(to_remove)} duplicate files...")
        removed = 0
        for item, path, _ in to_remove:
            try:
                os.remove(path)
                item.remove(delete=False)  # Already deleted; remove from library
                removed += 1
            except OSError as e:
                print(f"  Error removing {path}: {e}", file=sys.stderr)
        print(f"Removed {removed} duplicates." + (f" Backup at {backup_dir}" if not skip_backup else ""))

    return 0


if __name__ == "__main__":
    sys.exit(main())
