#!/usr/bin/env python3
"""
Sync public music indexers to Prowlarr.

These are search sites (TPB, LimeTorrents, etc.)—distinct from ngosang
tracker announce URLs, which go to qBittorrent. Prowlarr manages indexers
so Lidarr/music-requests can search multiple torrent sites.
"""
from __future__ import annotations

import os
import sys

import httpx

PROWLARR_URL = os.environ.get("PROWLARR_URL", "http://prowlarr:9696").rstrip("/")
PROWLARR_API_KEY = os.environ.get("PROWLARR_API_KEY", "")

COMMON_FIELDS = [
    {"name": "definitionFile", "value": None},
    {"name": "baseSettings.queryLimit", "value": 100},
    {"name": "baseSettings.grabLimit", "value": 100},
    {"name": "baseSettings.limitsUnit", "value": 0},
    {"name": "torrentBaseSettings.appMinimumSeeders", "value": 1},
    {"name": "torrentBaseSettings.seedTime", "value": 1},
    {"name": "torrentBaseSettings.packSeedTime", "value": 1},
    {"name": "torrentBaseSettings.preferMagnetUrl", "value": True},
]

INDEXERS = [
    ("1337x", "1337x"),
    ("LimeTorrents", "limetorrents"),
    ("BT.etree", "btetree"),
    ("Torrent Downloads", "torrentdownloads"),
    ("BitSearch", "bitsearch"),
    ("Nyaa.si", "nyaasi"),
    ("Nipponsei", "nipponsei"),
    ("ExtraTorrent.st", "extratorrent-st"),
    ("Isohunt2", "isohunt2"),
    ("RuTracker", "rutracker-ru"),  # Large Russian tracker, good for music
]

# Indexer-specific extra fields (definition -> list of {name, value})
EXTRA_FIELDS: dict[str, list[dict]] = {
    "rutracker-ru": [
        {"name": "stripcyrillic", "value": False},
        {"name": "addrussiantotitle", "value": True},
        {"name": "torrentBaseSettings.seedRatio", "value": 1.0},
    ],
}


def add_indexer(client: httpx.Client, name: str, definition: str) -> bool:
    fields = [f.copy() for f in COMMON_FIELDS]
    fields[0]["value"] = definition
    for extra in EXTRA_FIELDS.get(definition, []):
        fields.append(extra)
    payload = {
        "name": name,
        "definitionName": definition,
        "implementation": "Cardigann",
        "configContract": "CardigannSettings",
        "enable": True,
        "priority": 25,
        "appProfileId": 1,
        "tags": [],
        "fields": [{"name": f["name"], "value": f["value"]} for f in fields],
    }
    r = client.post(f"{PROWLARR_URL}/api/v1/indexer", json=payload, timeout=30)
    if r.status_code in (200, 201):
        print(f"  Added: {name}")
        return True
    print(f"  Failed {name}: {r.status_code} {r.text[:200]}")
    return False


def main() -> int:
    if not PROWLARR_API_KEY:
        print("Set PROWLARR_API_KEY environment variable.", file=sys.stderr)
        return 1

    headers = {"X-Api-Key": PROWLARR_API_KEY}
    with httpx.Client(headers=headers) as client:
        r = client.get(f"{PROWLARR_URL}/api/v1/indexer", timeout=10)
        r.raise_for_status()
        existing = {i["name"] for i in r.json()}

    print(f"Existing Prowlarr indexers: {', '.join(sorted(existing))}")
    added = 0
    with httpx.Client(headers=headers) as client:
        for name, definition in INDEXERS:
            if name in existing:
                print(f"  Skip (exists): {name}")
                continue
            if add_indexer(client, name, definition):
                added += 1

    print(f"\nAdded {added} indexers to Prowlarr.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
