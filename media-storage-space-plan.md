# Media storage: getting to ≤90% usage (for backup eligibility)

## Target
- **Current:** ~99% used (~114 GB free on 10 TB)
- **Need:** ≤90% used → **free ~973 GB** (so ~1 TB free total)

## Where space is (rough)
| Location        | Size   | Notes                          |
|----------------|--------|---------------------------------|
| **downloads**  | **6.4 TB** | Torrent/client download folder |
| movies         | 4.7 TB | Library                         |
| tvshows        | 1.8 TB | Library                         |
| music          | 975 GB | Library                         |
| transcodes     | 1.9 GB | Jellyfin temp (safe to clear)   |
| .dedupe-backup | 858 MB | Old dedupe run (review then delete) |

## Ways to free ~1 TB

### 1. **Downloads folder (biggest lever – 6.4 TB)** ✅ Duplicates identified
- **Investigation done:** 1,094 files in `downloads/` have the **same size and filename** as files in `movies/` or `tvshows/` → they are almost certainly copies of already-imported content.
- **Total duplicate size: ~2,089 GB (~2.09 TB).** Removing these would bring the volume well under 90%.
- **Scripts:**
  - `list-download-duplicates.sh` – (re)builds the list of duplicate paths → writes `/tmp/download_duplicate_paths.txt`.
  - `remove-download-duplicates.sh [--dry-run] [path_list]` – deletes (or with `--dry-run` only prints) those paths. Default list: `/tmp/download_duplicate_paths.txt`.
- **Options:**
  - Run `remove-download-duplicates.sh --dry-run` to see what would be removed, then run without `--dry-run` when ready. Be aware: if any torrents are still seeding, removing files will break those torrents.
  - **Change workflow:** set Radarr/Sonarr to **move** (or hardlink) instead of copy so future downloads don’t double space.

### 2. **More compression (library only)**
- One big 1080p REMUX (e.g. 45 GB) → H.264/AAC often saves **~25–35 GB** per movie.
- **Godfather** run in progress: will save ~30–40 GB when done.
- To free **~973 GB** from compression alone you’d need on the order of **25–35** such compressions (or fewer if some are 50+ GB).
- **Ways to do it:**
  - Let **nightly compress** run every night (3–7 AM); it does one file per night, skips failures and tries the next.
  - Run **one-shot compressions** for the next largest 1080p REMUXes (we have a list); you can run several in sequence or stagger them.

### 3. **Quick, safe cleanups**
- **Transcodes:** `rm -rf /mnt/media-storage/transcodes/*` frees **~1.9 GB**. Jellyfin will recreate as needed.
- **.dedupe-backup:** **~858 MB**. Only remove after you’re sure dedupe results are correct and you don’t need to roll back.

### 4. **Replace large movie with smaller release (Apibay + qBittorrent)**
- **Script:** `replace-movie-with-smaller.sh` (or `replace-movie-with-smaller.py`) picks the largest movie in the library, searches The Pirate Bay (Apibay), adds a much smaller release to qBittorrent, waits for completion, then replaces the file in the library and deletes the old one.
- **Usage:** `./replace-movie-with-smaller.sh` (full run); `--dry-run` to preview; `--add-only` to add the torrent and exit without waiting/replacing. If qBittorrent runs in Docker: `export QBIT_SAVE_PATH_REPLACEMENT=/downloads/replacement-movies`.
- **Env:** `MIN_SIZE_GB`, `MAX_SIZE_RATIO`, `MIN_SEEDERS`, `QBIT_HOST`, etc. See script docstring.

### 5. **One-time / manual**
- Delete or archive **low-priority content** (e.g. old TV seasons, movies you don’t need in library) to free space quickly.
- If you have **another volume or NAS**, move `downloads` (or old completed downloads) there so this volume drops below 90%, run the backup, then decide policy (move vs copy, retention).

## Suggested order
1. **Confirm Radarr/Sonarr behavior** (copy vs move/hardlink from downloads).
2. **Clear transcodes** (small, safe).
3. **Plan downloads:** either remove/trim completed imports, or move downloads off this volume to get under 90% and take the backup.
4. **Keep compression running** (nightly + optional one-shots) so library size keeps shrinking over time.
