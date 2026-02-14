#!/usr/bin/env python3
"""Add public music trackers to Prowlarr via API."""
import os
import requests

PROWLARR_URL = os.environ.get("PROWLARR_URL", "http://localhost:9696").rstrip("/")
PROWLARR_API_KEY = os.environ.get("PROWLARR_API_KEY", "")

# Standard fields for Cardigann public indexers (no API key needed)
COMMON_FIELDS = [
    {"name": "definitionFile", "value": None},  # set per indexer
    {"name": "baseSettings.queryLimit", "value": 100},
    {"name": "baseSettings.grabLimit", "value": 100},
    {"name": "baseSettings.limitsUnit", "value": 0},
    {"name": "torrentBaseSettings.appMinimumSeeders", "value": 1},
    {"name": "torrentBaseSettings.seedTime", "value": 1},
    {"name": "torrentBaseSettings.packSeedTime", "value": 1},
    {"name": "torrentBaseSettings.preferMagnetUrl", "value": True},
]

INDEXERS = [
    ("1337x", "1337x", "Public torrent site with verified downloads, good for music"),
    ("LimeTorrents", "limetorrents", "Public general torrent index, often has music"),
    ("BT.etree", "btetree", "Dedicated to bootleg FLAC/lossless music"),
    ("Torrent Downloads", "torrentdownloads", "Public site for all content including music"),
    ("BitSearch", "bitsearch", "Public meta-search engine (searches multiple sites)"),
    ("Nyaa.si", "nyaasi", "Eastern Asian media including anime soundtracks and J-pop"),
    ("Nipponsei", "nipponsei", "Music fresh from Japan"),
    ("ExtraTorrent.st", "extratorrent-st", "Public tracker for movies/TV/general"),
    ("Isohunt2", "isohunt2", "Public torrent search for movies/TV/general"),
    ("RuTracker", "rutracker-ru", "Large Russian tracker, good for music (may need manual RuTracker.org + login)"),
]

def add_indexer(name: str, definition: str, description: str) -> bool:
    fields = [f.copy() for f in COMMON_FIELDS]
    fields[0]["value"] = definition

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
    r = requests.post(
        f"{PROWLARR_URL}/api/v1/indexer",
        json=payload,
        headers={"X-Api-Key": PROWLARR_API_KEY},
        timeout=30,
    )
    if r.status_code in (200, 201):
        print(f"  Added: {name}")
        return True
    print(f"  Failed {name}: {r.status_code} {r.text[:200]}")
    return False

def main():
    if not PROWLARR_API_KEY:
        print("Set PROWLARR_API_KEY env var")
        return 1

    # Get existing indexers
    r = requests.get(
        f"{PROWLARR_URL}/api/v1/indexer",
        headers={"X-Api-Key": PROWLARR_API_KEY},
        timeout=10,
    )
    r.raise_for_status()
    existing = {i["name"] for i in r.json()}
    print(f"Existing: {', '.join(existing)}")
    print()

    added = 0
    for name, definition, _desc in INDEXERS:
        if name in existing:
            print(f"  Skip (exists): {name}")
            continue
        if add_indexer(name, definition, _desc):
            added += 1

    print(f"\nAdded {added} indexers.")
    return 0

if __name__ == "__main__":
    exit(main())
