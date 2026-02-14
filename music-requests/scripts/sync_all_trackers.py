#!/usr/bin/env python3
"""
Sync all tracker/indexer sources into the media stack.

1. ngosang/trackerslist → qBittorrent (announce URLs for peer discovery)
2. Music indexers → Prowlarr (search sites: TPB, LimeTorrents, etc.)

Run manually or via cron. Uses same env vars as music-requests (QBIT_*, PROWLARR_*).
"""
from __future__ import annotations

import os
import subprocess
import sys

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))


def run(name: str, script: str) -> int:
    code = subprocess.call(
        [sys.executable, os.path.join(SCRIPTS_DIR, script)],
        env=os.environ,
    )
    if code != 0:
        print(f"[{name}] exited with {code}", file=sys.stderr)
    return code


def main() -> int:
    print("=== Sync ngosang trackers → qBittorrent ===")
    c1 = run("ngosang", "sync_ngosang_trackers.py")

    print("\n=== Sync music indexers → Prowlarr ===")
    c2 = run("prowlarr", "sync_prowlarr_indexers.py")

    if c1 != 0 or c2 != 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
