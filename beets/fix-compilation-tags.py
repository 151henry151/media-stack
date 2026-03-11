#!/usr/bin/env python3
"""
Write albumartist (TPE2) and comp tags to files for compilations.
Substreamer/Airsonic group by albumartist; when missing they use artist,
causing VA albums to show as many one-track albums.

Uses mediafile directly for speed. Run as root (or user with access to
music dir) since /mnt/media-storage may have restricted permissions.
"""
import os
import sys

# Use beets venv for mediafile
sys.path.insert(0, "/home/henry/beets-venv/lib/python3.11/site-packages")

from beets.library import Library
from beets.util import syspath
from mediafile import MediaFile


def main():
    lib_path = "/home/henry/.config/beets/musiclibrary.db"
    lib = Library(lib_path)
    written = 0
    missing = 0

    for item in lib.items():
        if not item.comp and not (item.albumartist and "Various" in str(item.albumartist)):
            continue
        p = syspath(item.path)
        if not os.path.exists(p):
            missing += 1
            continue
        try:
            m = MediaFile(p)
            if m.albumartist != item.albumartist or m.comp != item.comp:
                m.albumartist = item.albumartist or "Various Artists"
                m.comp = item.comp if item.comp is not None else True
                m.save()
                written += 1
                if written <= 5:
                    print(f"Wrote: {item.albumartist} - {os.path.basename(p)}")
        except Exception as e:
            print(f"Error {p}: {e}", file=sys.stderr)

    print(f"Written: {written}, missing: {missing}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
