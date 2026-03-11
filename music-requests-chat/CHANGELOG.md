# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Support pasted list of artist names (newline- or comma-separated): add discography or first available torrent for each artist (up to 30 per paste).
- Delay notice in replies: inform users it may be a day or two before music appears on the server.

### Changed

- Fall back to `requests` for backend HTTP calls when `httpx` is unavailable so the chat service still starts in minimal Python environments.

## [0.1.0] - 2026-03-05

### Added

- Chat UI for music-requests: login with Airsonic credentials, request albums in plain language.
- "Add [album] by [artist]" flow: artist search, album list, TPB search, optional YouTube rip.
- "Search artist X" and paste YouTube/archive.org URL for playlist/archive rip.
- Session cookie auth; proxy to music-requests backend with Basic auth.
- Attachments in chat: artist images, album cover, torrent list.
- Systemd unit and run script for deployment.
