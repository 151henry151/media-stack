# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Require English audio for movie and TV picks: only suggest torrents whose names indicate English (e.g. "english", "eng", "dual audio", "dubbed").

### Changed

- Use qBittorrent category `radarr` for movies and `tv-sonarr` for TV shows so Radarr/Sonarr pick them up correctly.

## [0.1.0] - 2025-03-05

### Added

- Chat-style web UI at requests.romptele.com for requesting movies and TV shows.
- Invite-only registration with SQLite-backed users and invite codes; JWT authentication.
- Apibay (The Pirate Bay) search for movies (category 207) and TV (category 199).
- Movie selection: prefer &lt;5GB, at least one seeder, prefer more seeders.
- TV selection: prefer smallest size and full-season torrents when present; at least one seeder.
- Confirmation flow: bot proposes one torrent (name, size, seeders); user confirms or rejects; on confirm, add magnet to qBittorrent with category radarr (movies) or sonarr (TV), save path /downloads, add to top of queue.
- Admin endpoint POST /api/admin/invite (JSON body `{"code": "..."}`) for creating invite codes (requires auth).
- Nginx config template for requests.romptele.com proxying to port 8002.
- Dockerfile and README with run instructions and environment variables.
