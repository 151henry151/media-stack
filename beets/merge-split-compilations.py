#!/usr/bin/env python3
"""
Merge split compilation albums into single VA compilations.

Albums like "Unforgettable Instrumental Hits" or "Stormy Weather" that have
the same album name but different albumartist per track get split into many
one-track "albums" in Substreamer. This script:
1. Identifies such albums (same album name, 3+ distinct albumartists)
2. Sets albumartist=Various Artists, comp=1
3. Moves files to Compilations/$album/
4. Writes tags to files

Run as root (music dir may have restricted permissions).
"""
import os
import shutil
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, "/home/henry/beets-venv/lib/python3.11/site-packages")

from beets.library import Library
from beets.util import syspath
from mediafile import MediaFile

MUSIC_ROOT = Path("/mnt/media-storage/music")
COMP_DIR = MUSIC_ROOT / "Compilations"
VA_NAME = "Various Artists"


def main():
    dry_run = "--dry-run" in sys.argv
    if dry_run:
        print("DRY RUN - no changes will be made\n")

    lib = Library("/home/henry/.config/beets/musiclibrary.db")

    # Find albums with same name but multiple albumartists (split compilations)
    by_album = defaultdict(list)
    for item in lib.items():
        by_album[item.album].append(item)

    to_merge = []
    for album_name, items in by_album.items():
        albumartists = set((i.albumartist or i.artist or "").strip() for i in items)
        track_artists = set((i.artist or "").strip() for i in items)
        albumartists.discard("")
        track_artists.discard("")
        # Merge when: 3+ distinct albumartists (split) OR 3+ track artists (mis-tagged as single artist)
        # e.g. "Traditional Christmas - Volume Three" has albumartist=Ella but many track artists
        if len(albumartists) >= 3 or (len(track_artists) >= 3 and VA_NAME not in albumartists):
            to_merge.append((album_name, items))

    if not to_merge:
        print("No split compilations found.")
        return 0

    print(f"Found {len(to_merge)} split compilation(s) to merge:")
    for album_name, items in to_merge:
        aas = set((i.albumartist or i.artist) for i in items)
        tas = set(i.artist for i in items if i.artist)
        print(f"  - {album_name}: {len(items)} tracks, {len(aas)} albumartists, {len(tas)} track artists")

    for album_name, items in to_merge:
        dest_dir = COMP_DIR / album_name
        dest_dir.mkdir(parents=True, exist_ok=True)

        # Sort by (artist, track, title) for consistent ordering
        items_sorted = sorted(items, key=lambda i: ((i.artist or ""), i.track or 0, (i.title or "")))

        # Two-phase move: first to temp (avoids overwriting when dest_dir already has files)
        import tempfile
        moves = []  # (src_path, item, idx)
        if dry_run:
            for idx, item in enumerate(items_sorted, 1):
                src = Path(syspath(item.path))
                if src.exists():
                    moves.append((src, item, idx))
                else:
                    print(f"  Skip (missing): {src}")
            # Phase 2 (dry run): just print
            for tmp_src, item, idx in moves:
                title = (item.title or "Unknown").replace("/", "-")
                track_str = str(idx).zfill(2)
                dest_name = f"{track_str} - {title}{tmp_src.suffix}"
                print(f"  Would move: {item.title} -> {dest_name}")
        else:
            with tempfile.TemporaryDirectory(dir=dest_dir.parent) as tmpdir:
                tmpdir = Path(tmpdir)
                for idx, item in enumerate(items_sorted, 1):
                    src = Path(syspath(item.path))
                    if not src.exists():
                        print(f"  Skip (missing): {src}")
                        continue
                    tmp_dest = tmpdir / f"_merge_{idx:03d}{src.suffix}"
                    try:
                        shutil.move(str(src), str(tmp_dest))
                        moves.append((tmp_dest, item, idx))
                    except OSError as e:
                        print(f"  Move to temp failed {src}: {e}", file=sys.stderr)

                # Phase 2: move from temp to final dest (inside with - temp still exists)
                for tmp_src, item, idx in moves:
                    ext = tmp_src.suffix
                    title = (item.title or "Unknown").replace("/", "-")
                    track_str = str(idx).zfill(2)
                    dest_name = f"{track_str} - {title}{ext}"
                    dest = dest_dir / dest_name
                    if dest.exists():
                        artist_suffix = (item.artist or "Unknown").replace("/", "-")[:30]
                        dest_name = f"{track_str} - {title} ({artist_suffix}){ext}"
                        dest = dest_dir / dest_name
                        n = 1
                        while dest.exists():
                            dest = dest_dir / f"{track_str} - {title} ({artist_suffix} {n}){ext}"
                            n += 1

                    try:
                        shutil.move(str(tmp_src), str(dest))
                        item.path = bytes(str(dest), "utf-8")
                        item.albumartist = VA_NAME
                        item.comp = True
                        item.track = idx
                        item.tracktotal = len(items_sorted)
                        item.store()
                    except OSError as e:
                        print(f"  Move failed {tmp_src} -> {dest}: {e}", file=sys.stderr)
                        continue

                    try:
                        m = MediaFile(str(dest))
                        m.albumartist = VA_NAME
                        m.comp = True
                        m.track = idx
                        m.tracktotal = len(items_sorted)
                        m.save()
                    except Exception as e:
                        print(f"  Tag write failed {dest}: {e}", file=sys.stderr)

        # Remove empty source dirs
        for item in items:
            src = Path(syspath(item.path))
            old_dir = Path(syspath(items[0].path)).parent if items else None
            # We already moved - get original parent from first item's original path
            pass
        # Collect and remove empty dirs - we'd need to track original paths
        print(f"  Merged: {album_name} -> {dest_dir}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
