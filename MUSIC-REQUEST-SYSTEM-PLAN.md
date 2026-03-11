# Music Request System – Plan

## Current Flow (Manual)

1. You look up magnet links on The Pirate Bay (or have me use Apibay)
2. Add magnets to qBittorrent with category `lidarr`
3. `lidarr-torrent-import.sh` runs on cron → beets → music library → Airsonic

## Desired Flow

1. **User** (signed into Airsonic) clicks **Request**
2. **Request page**: search artist (MusicBrainz/Discogs – any artist)
3. Pick **artist** → choose request type:
   - **Album** – see albums from MusicBrainz → pick album → TPB search for that album → add chosen magnet
   - **Discography** – TPB search for `"Artist Name Discography"` → show results (name, size, seeders, etc.) → user picks which one → add magnet
4. Magnet added to qBittorrent (category `lidarr`)
5. Existing import pipeline does the rest (beets → Airsonic)

---

## Phase 1: Prowlarr + The Pirate Bay + Lidarr

**Goal:** Lidarr can search TPB via Prowlarr, so you can add albums from Lidarr’s UI as an alternative to manual magnets.

**Status:** Prowlarr and Lidarr are running (ports 9696, 8686). TPB is supported in Prowlarr.

### Step 1: Add The Pirate Bay to Prowlarr

1. Open **Prowlarr**: https://prowlarr.romptele.com (or http://localhost:9696)
2. **Indexers** → **Add Indexer**
3. Search for **The Pirate Bay**
4. Add it (no API key required for TPB)
5. Save

### Step 2: Connect Lidarr to Prowlarr

1. In **Prowlarr** → **Settings** → **Apps**
2. Click **+**
3. Choose **Lidarr**
4. Configure:
   - **Name:** Lidarr
   - **Sync Level:** Add and Remove Only (or Full Sync)
   - **Prowlarr Server:** `http://prowlarr:9696` (or `http://localhost:9696` if not in Docker)
   - **Lidarr Server:** `http://localhost:8686` (or your Lidarr URL)
   - **API Key:** From Lidarr → Settings → General → Security
5. **Test** → **Save**

After this, Lidarr will receive Prowlarr’s indexers (including TPB) and can search them when adding artists/albums.

---

## Phase 2: Custom Music Request App

**Goal:** Airsonic users can request music via a Jellyseerr-like flow without using Lidarr directly.

**Architecture:**

```
┌─────────────────┐     ┌──────────────────────┐     ┌─────────────────┐
│  Airsonic User  │────▶│  Music Request App   │────▶│  qBittorrent    │
│  (Request btn)  │     │  - MusicBrainz API   │     │  (magnet+cat)   │
└─────────────────┘     │  - Apibay (TPB API)  │     └────────┬────────┘
                        │  - Subsonic API      │              │
                        │    (auth)            │              ▼
                        └──────────────────────┘     lidarr-torrent-import
                                                              │
                                                              ▼
                                                     beets → Airsonic
```

### Components

| Component | Purpose |
|-----------|---------|
| **Auth** | Use Subsonic API to verify Airsonic username/password (e.g. `ping.view`) |
| **Artist search** | MusicBrainz API: `GET /ws/2/artist/?query=...&fmt=json` |
| **Album list** | MusicBrainz API: `GET /ws/2/release-group/?artist=<mbid>&fmt=json` |
| **TPB search** | Apibay API: `https://apibay.org/q.php?q=Artist+Album` (or `Artist+Discography`) |
| **Add torrent** | qBittorrent API: add magnet with category `lidarr` |

### Discography Request Flow

When the user selects **Discography** for an artist (e.g. Bon Jovi):

1. Search TPB for `"Artist Name Discography"` (e.g. `"Bon Jovi Discography"`)
2. Display results (name, size, seeders, leechers, date)
3. User picks one from the list
4. Add chosen magnet to qBittorrent (category `lidarr`)

This lets users grab full discography torrents when available (often better than requesting albums one by one).

### Implementation Options

**A) Standalone web app (recommended)**  
- Backend: Python (FastAPI) or Node.js  
- Frontend: React or simple HTML/JS  
- Hosted at e.g. `music-requests.romptele.com` or `music.romptele.com/request`  
- Users log in with Airsonic credentials; app verifies via Subsonic API  

**B) Integrate into existing stack**  
- Could live under `promptele.com/music-requests` if you have a main site  
- Or as a subpath of the music domain  

### “Request” Button in Airsonic

Airsonic’s UI is not easily extensible. Options:

- Add a visible **Request** link in a custom header/branding area (if you use one)
- Put the link in the footer or sidebar via custom CSS/JS injection (if supported)
- Document the URL (e.g. `https://music-requests.romptele.com`) and share it with users
- Use a redirect or landing page that shows both “Listen” (Airsonic) and “Request” links

### Tech Stack (Suggested)

- **Backend:** Python FastAPI
- **Frontend:** Vanilla JS or lightweight framework (e.g. Alpine.js)
- **APIs:** MusicBrainz (no key), Apibay (no key), qBittorrent (existing), Subsonic (auth)

---

## Implementation Status

- **Phase 1:** ✓ Complete. The Pirate Bay is in Prowlarr, Lidarr is connected.
- **Phase 2:** ✓ Complete. Music Request app deployed at https://music-requests.romptele.com

## Next Steps (if expanding)
   - Preferred host (e.g. `music-requests.romptele.com`)
   - Tech preference (Python vs Node)
   - How you want the “Request” entry point exposed (link, subpath, etc.)
