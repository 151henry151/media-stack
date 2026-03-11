"""
Media Request Chat – request movies/TV via chat; Apibay search + qBittorrent.
- Invite-only registration, JWT auth.
- User says what they want → bot finds a torrent (movies &lt;5GB prefer, TV smallest season, ≥1 seeder) → user confirms → add to qBittorrent (radarr/sonarr).
"""
from __future__ import annotations

import os
import re
import sqlite3
import time
import urllib.parse
from contextlib import asynccontextmanager
from pathlib import Path

import requests
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

try:
    import qbittorrentapi
except ImportError:
    qbittorrentapi = None  # type: ignore
try:
    import bcrypt
except ImportError:
    bcrypt = None  # type: ignore

# --- Config ---
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("MEDIA_REQUESTS_DB", str(BASE_DIR / "media_requests.db")))
JWT_SECRET = os.environ.get("MEDIA_REQUESTS_JWT_SECRET", "change-me-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 168  # 1 week
APIBAY_BASE = "https://apibay.org"
APIBAY_CAT_MOVIES = 207
APIBAY_CAT_TV = 199
QBIT_HOST = os.environ.get("QBIT_HOST", "localhost:5080")
QBIT_USER = os.environ.get("QBIT_USER", "admin")
QBIT_PASS = os.environ.get("QBIT_PASS", "admin123")
PREFER_MOVIE_MAX_GB = 5.0
MIN_SEEDERS = 1
PREFER_SEEDERS = 5
USER_AGENT = "MediaRequests/1.0 (https://requests.romptele.com)"

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)
SESSION = requests.Session()
SESSION.headers["User-Agent"] = USER_AGENT

# In-memory: user_id -> { torrent dict, type "movie"|"tv" } for confirmation step
_pending: dict[int, dict] = {}


def _init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at REAL NOT NULL
        )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS invite_codes (
            code TEXT PRIMARY KEY,
            used_at REAL,
            used_by_user_id INTEGER,
            created_at REAL NOT NULL,
            FOREIGN KEY (used_by_user_id) REFERENCES users(id)
        )"""
        )
        cur = conn.execute("SELECT 1 FROM invite_codes LIMIT 1")
        if not cur.fetchone():
            conn.execute(
                "INSERT INTO invite_codes (code, created_at) VALUES (?, ?)",
                (os.environ.get("MEDIA_REQUESTS_FIRST_INVITE", "welcome"), time.time()),
            )
        conn.commit()


def _create_invite_code(code: str) -> bool:
    with sqlite3.connect(DB_PATH) as conn:
        try:
            conn.execute(
                "INSERT INTO invite_codes (code, created_at) VALUES (?, ?)",
                (code.strip().lower(), time.time()),
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False


def _use_invite_code(code: str, user_id: int) -> bool:
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            "UPDATE invite_codes SET used_at = ?, used_by_user_id = ? WHERE code = ? AND used_at IS NULL",
            (time.time(), user_id, code.strip().lower()),
        )
        conn.commit()
        return cur.rowcount > 0


def _is_invite_valid(code: str) -> bool:
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute("SELECT 1 FROM invite_codes WHERE code = ? AND used_at IS NULL", (code.strip().lower(),))
        return cur.fetchone() is not None


def _register_user(username: str, password: str, invite_code: str) -> int | None:
    code = invite_code.strip().lower()
    if not _is_invite_valid(code):
        return None
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
            (username.strip(), pwd_ctx.hash(password), time.time()),
        )
        user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "UPDATE invite_codes SET used_at = ?, used_by_user_id = ? WHERE code = ? AND used_at IS NULL",
            (time.time(), user_id, code),
        )
        conn.commit()
    return user_id


def _get_user_by_username(username: str) -> tuple[int, str] | None:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute("SELECT id, password_hash FROM users WHERE username = ?", (username.strip(),)).fetchone()
        return (row[0], row[1]) if row else None


def _verify_password(plain: str, hashed: str) -> bool:
    if hashed.startswith("$2b$") and bcrypt is not None:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    return pwd_ctx.verify(plain, hashed)


def _create_jwt(user_id: int, username: str) -> str:
    payload = {"sub": str(user_id), "username": username, "exp": time.time() + JWT_EXPIRE_HOURS * 3600}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _decode_jwt(token: str) -> dict | None:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError:
        return None


# --- Apibay ---
def _search_apibay(query: str, cat: int) -> list[dict]:
    try:
        r = SESSION.get(f"{APIBAY_BASE}/q.php", params={"q": query, "cat": cat}, timeout=15)
        r.raise_for_status()
        data = r.json()
    except Exception:
        return []
    if isinstance(data, dict):
        data = [data]
    return [t for t in data if t.get("id") and t["id"] != "0" and t.get("info_hash")]


def _is_video_name(name: str) -> bool:
    n = (name or "").lower()
    if any(ext in n for ext in (".mkv", ".mp4", ".avi", ".m4v")):
        return True
    return any(kw in n for kw in ("1080p", "720p", "2160p", "4k", "bluray", "web-dl", "remux", "x264", "x265", "hevc"))


def _has_english_audio(name: str) -> bool:
    """Return True if the torrent name suggests English audio (so we avoid sub-only or non-English releases)."""
    n = (name or "").lower()
    if "english" in n or " eng " in n or " eng." in n or ".eng " in n or "[eng]" in n or "(eng)" in n:
        return True
    if "dual audio" in n or "dual.audio" in n or "dual-audio" in n:
        return True
    if "dubbed" in n or " english dub" in n or " eng dub" in n or " dub " in n:
        return True
    return False


def _pick_movie(torrents: list[dict]) -> dict | None:
    prefer_max = int(PREFER_MOVIE_MAX_GB * 1024**3)
    candidates = []
    for t in torrents:
        size = int(t.get("size") or 0)
        if size <= 0:
            continue
        seeders = int(t.get("seeders") or 0)
        if seeders < MIN_SEEDERS:
            continue
        name = (t.get("name") or "").strip()
        if not _is_video_name(name):
            continue
        # For movies (cat 207) we don't require "English" in the name; most movie torrents are unmarked.
        score = seeders
        if _has_english_audio(name):
            score += 10
        if "720" in name or "720p" in name.lower():
            score += 30
        if seeders >= PREFER_SEEDERS:
            score += 20
        if size < prefer_max:
            score += 50
        candidates.append((score, -size, t))
    if not candidates:
        return None
    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return candidates[0][2]


def _pick_tv(torrents: list[dict]) -> dict | None:
    """Prefer smallest torrent with at least one seeder (prefer full season in name when present)."""
    candidates = []
    for t in torrents:
        size = int(t.get("size") or 0)
        if size <= 0:
            continue
        seeders = int(t.get("seeders") or 0)
        if seeders < MIN_SEEDERS:
            continue
        name = (t.get("name") or "").strip().lower()
        if not _is_video_name(name) or not _has_english_audio(name):
            continue
        is_full_season = "season" in name or "s01" in name or "s1 " in name or " complete " in name
        candidates.append((size, -seeders, 0 if is_full_season else 1, t))  # full season first, then size, then seeders
    if not candidates:
        return None
    candidates.sort(key=lambda x: (x[2], x[0], x[1]))  # full-season first, then smallest, then more seeders
    return candidates[0][3]


def _build_magnet(info_hash: str, name: str) -> str:
    info_hash = (info_hash or "").strip().upper()
    if len(info_hash) != 40 or not re.match(r"^[0-9A-Fa-f]+$", info_hash):
        return ""
    dn = urllib.parse.quote(name or "torrent", safe="")
    return f"magnet:?xt=urn:btih:{info_hash}&dn={dn}"


def _add_to_qbit(magnet: str, category: str) -> None:
    if not qbittorrentapi:
        raise RuntimeError("qbittorrent-api not installed")
    host, _, port = QBIT_HOST.partition(":")
    port = int(port) if port else 5080
    client = qbittorrentapi.Client(host=host or "localhost", port=port, username=QBIT_USER, password=QBIT_PASS)
    client.auth_log_in()
    save_path = "/downloads"
    client.torrents_add(urls=magnet, category=category, save_path=save_path, add_to_top_of_queue=True)


def _search_and_pick(query: str, is_tv: bool) -> tuple[dict | None, str]:
    cat = APIBAY_CAT_TV if is_tv else APIBAY_CAT_MOVIES
    torrents = _search_apibay(query.strip(), cat)
    if not torrents:
        return None, "No results found for that search."
    chosen = _pick_tv(torrents) if is_tv else _pick_movie(torrents)
    if not chosen:
        return None, "No suitable torrent found (need at least one seeder and a video release)."
    return chosen, ""


# --- Pydantic ---
class RegisterRequest(BaseModel):
    invite_code: str
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class ChatRequest(BaseModel):
    message: str


# --- App ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    _init_db()
    yield


app = FastAPI(title="Media Requests", lifespan=lifespan)
static_dir = BASE_DIR / "static"
if static_dir.is_dir():
    from fastapi.staticfiles import StaticFiles
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


def get_current_user(creds: HTTPAuthorizationCredentials | None = Depends(security)):
    if not creds or not creds.credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = _decode_jwt(creds.credentials)
    if not payload or "sub" not in payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    return {"user_id": int(payload["sub"]), "username": payload.get("username", "")}


@app.get("/", response_class=HTMLResponse)
async def index():
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.post("/api/register")
async def register(req: RegisterRequest):
    if not req.invite_code.strip() or not req.username.strip() or not req.password:
        raise HTTPException(status_code=400, detail="Invite code, username and password required")
    if not _is_invite_valid(req.invite_code):
        raise HTTPException(status_code=400, detail="Invalid or already used invite code")
    with sqlite3.connect(DB_PATH) as conn:
        if conn.execute("SELECT id FROM users WHERE username = ?", (req.username.strip(),)).fetchone():
            raise HTTPException(status_code=400, detail="Username already taken")
    user_id = _register_user(req.username, req.password, req.invite_code)
    if not user_id:
        raise HTTPException(status_code=400, detail="Registration failed")
    token = _create_jwt(user_id, req.username.strip())
    return {"ok": True, "token": token, "username": req.username.strip()}


@app.post("/api/login")
async def login(req: LoginRequest):
    row = _get_user_by_username(req.username)
    if not row or not _verify_password(req.password, row[1]):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    user_id = row[0]
    token = _create_jwt(user_id, req.username.strip())
    return {"ok": True, "token": token, "username": req.username.strip()}


CONFIRM_PATTERNS = re.compile(r"\b(yes|yeah|yep|correct|right|looks good|add it|do it|confirm|please add)\b", re.I)
REJECT_PATTERNS = re.compile(r"\b(no|nope|wrong|different|other|cancel)\b", re.I)


def _normalize_query(msg: str) -> str:
    msg = msg.strip()
    # Strip surrounding quotes so "Add 'free willy'" -> free willy
    if len(msg) >= 2 and (msg[0], msg[-1]) in (("'", "'"), ('"', '"')):
        msg = msg[1:-1].strip()
    for prefix in ("add ", "i want ", "want ", "get ", "find ", "search ", "movie ", "show ", "tv "):
        if msg.lower().startswith(prefix):
            msg = msg[len(prefix):].strip()
    return msg or msg


@app.post("/api/chat")
async def chat(req: ChatRequest, user: dict = Depends(get_current_user)):
    msg = (req.message or "").strip()
    if not msg:
        return {"reply": "Send a message to request a movie or TV show (e.g. \"Add The Matrix\" or \"I want Breaking Bad season 1\")."}

    user_id = user["user_id"]
    pending = _pending.get(user_id)

    if pending and CONFIRM_PATTERNS.search(msg):
        torrent = pending.get("torrent")
        kind = pending.get("type", "movie")
        if not torrent:
            _pending.pop(user_id, None)
            return {"reply": "No pending request. Tell me what movie or show you want."}
        magnet = _build_magnet(torrent.get("info_hash", ""), torrent.get("name", ""))
        if not magnet:
            _pending.pop(user_id, None)
            return {"reply": "Something went wrong building the magnet link. Try again."}
        try:
            _add_to_qbit(magnet, "tv-sonarr" if kind == "tv" else "radarr")
        except Exception as e:
            return {"reply": f"Failed to add to download manager: {e}"}
        _pending.pop(user_id, None)
        return {"reply": "I've added it to the download manager. It may be a day or two before it appears on the server."}

    if pending and REJECT_PATTERNS.search(msg):
        _pending.pop(user_id, None)
        return {"reply": "No problem. What would you like to add instead?"}

    query = _normalize_query(msg)
    if len(query) < 2:
        return {"reply": "Please tell me the name of the movie or TV show (e.g. \"The Matrix\" or \"Breaking Bad S01\")."}

    is_tv = any(x in msg.lower() for x in ["season", "s01", "s1 ", " tv ", "show", "series"])
    chosen, err = _search_and_pick(query, is_tv)
    if err:
        return {"reply": err}

    name = chosen.get("name", "Unknown")
    size_b = int(chosen.get("size") or 0)
    seeders = int(chosen.get("seeders") or 0)
    size_gb = size_b / (1024**3)
    _pending[user_id] = {"torrent": chosen, "type": "tv" if is_tv else "movie"}
    return {
        "reply": f"I found this torrent: **{name}** — {size_gb:.2f} GB, {seeders} seeder(s). Does that look like the right one? (Say yes to add it, or no to try something else.)"
    }


# --- Admin: create invite code (any logged-in user can create invites) ---
class InviteRequest(BaseModel):
    code: str


@app.post("/api/admin/invite")
async def create_invite(req: InviteRequest, _: dict = Depends(get_current_user)):
    if not (req.code and req.code.strip()):
        raise HTTPException(status_code=400, detail="Invite code required")
    if _create_invite_code(req.code):
        return {"ok": True, "message": f"Invite code '{req.code.strip()}' created."}
    raise HTTPException(status_code=400, detail="Code already exists or invalid.")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8002")))
