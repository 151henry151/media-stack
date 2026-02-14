#!/usr/bin/env python3
"""
Sync public BitTorrent trackers from ngosang/trackerslist to qBittorrent.

The ngosang list provides tracker announce URLs (udp://..., https://...)
for peer discovery. These belong in qBittorrent's "Automatically add these
trackers to new downloads" setting—NOT in Prowlarr (which manages indexers,
i.e. search sites like TPB or 1337x).

Source: https://github.com/ngosang/trackerslist
Run manually or via cron to keep trackers up to date.
"""
from __future__ import annotations

import os
import sys
import urllib.request
from urllib.error import URLError

import qbittorrentapi

# Lists: trackers_best (20), trackers_all (119), trackers_all_udp, etc.
NGOSANG_BASE = "https://raw.githubusercontent.com/ngosang/trackerslist/master"
TRACKERS_LIST = os.environ.get("NGOSANG_LIST", "trackers_best")  # or trackers_all
QBIT_HOST = os.environ.get("QBIT_HOST", "qbittorrent:5080")
QBIT_USER = os.environ.get("QBIT_USER", "admin")
QBIT_PASS = os.environ.get("QBIT_PASS", "")


def fetch_trackers() -> list[str]:
    """Fetch tracker URLs from ngosang/trackerslist."""
    url = f"{NGOSANG_BASE}/{TRACKERS_LIST}.txt"
    req = urllib.request.Request(url, headers={"User-Agent": "MusicRequests/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        text = resp.read().decode()
    lines = [s.strip() for s in text.splitlines() if s.strip()]
    return lines


def apply_to_qbittorrent(trackers: list[str]) -> bool:
    """Set trackers in qBittorrent preferences. Enable add_trackers feature."""
    host, _, port = QBIT_HOST.partition(":")
    port = int(port) if port else 8080
    client = qbittorrentapi.Client(
        host=host or "localhost",
        port=port,
        username=QBIT_USER,
        password=QBIT_PASS,
    )
    client.auth_log_in()
    tracker_text = "\n".join(trackers)
    # Set both in one call to avoid resetting the other (qBittorrent API quirk)
    client.app_set_preferences(
        prefs={
            "add_trackers_enabled": True,
            "add_trackers": tracker_text,
        }
    )
    return True


def main() -> int:
    if not QBIT_PASS:
        print("Set QBIT_PASS (or QBIT_USER/QBIT_PASS) environment variable.", file=sys.stderr)
        return 1

    print(f"Fetching {TRACKERS_LIST}.txt from ngosang/trackerslist...")
    try:
        trackers = fetch_trackers()
    except URLError as e:
        print(f"Failed to fetch: {e}", file=sys.stderr)
        return 1

    if not trackers:
        print("No trackers returned.", file=sys.stderr)
        return 1

    print(f"Got {len(trackers)} trackers. Applying to qBittorrent at {QBIT_HOST}...")
    try:
        apply_to_qbittorrent(trackers)
    except qbittorrentapi.LoginFailed as e:
        print(f"qBittorrent login failed: {e}", file=sys.stderr)
        return 1
    except qbittorrentapi.APIConnectionError as e:
        print(f"Cannot reach qBittorrent: {e}", file=sys.stderr)
        return 1

    print("Done. New torrents will automatically get these trackers.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
