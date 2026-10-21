"""
Server for the Manila Noise Atlas dashboard.

Runs on the central Raspberry Pi (or any laptop) with only the Python
standard library:

    python software/dashboard/server.py                 # http://localhost:8000
    python software/dashboard/server.py --port 8080

Staff accounts (stored in data/live/users.json, passwords are hashed):

    python software/dashboard/server.py --add-user admin --role admin --name "Daryl Sebastian"
    python software/dashboard/server.py --add-user denr --role planner --name "DENR NCR"
    python software/dashboard/server.py --list-users
    python software/dashboard/server.py --remove-user denr

Roles
    admin    full dashboard, post public notices, edit sensor sites, see the activity log
    planner  full dashboard, planning report and activity log, read-only (for LGU, DENR, DOH)

Pages
    /                  public noise map for residents (index.html)
    /admin.html        staff dashboard (sign-in required)

API
    GET    /api/health                  used by the pages to detect this server
    GET    /api/readings/latest         newest reading per site
    GET    /api/readings/history        readings from the last 24 hours
    POST   /api/readings                add one reading (JSON object) or several (JSON list)
    POST   /api/login  /api/logout      staff sign-in (session cookie)
    GET    /api/me                      the signed-in user
    GET    /api/notices                 public notices that have not expired
    POST   /api/notices                 admin: post a notice
    DELETE /api/notices/<id>            admin: remove a notice
    GET    /api/sites                   site changes made by admins
    PUT    /api/sites/<id>              admin: add or update a site (name, coordinates, status, note)
    DELETE /api/sites/<id>              admin: remove a site
    GET    /api/log                     staff: activity log

If the environment variable NMA_DEVICE_KEY is set, POST /api/readings
requires the header "X-Device-Key: <that value>".
"""

from pathlib import Path
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from http.cookies import SimpleCookie
from datetime import datetime, timedelta, timezone
import argparse
import getpass
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import threading
import time

# =========================
# PATH SETUP
# =========================

BASE_DIR = Path(__file__).resolve().parents[2]
DASHBOARD_DIR = Path(__file__).resolve().parent
LIVE_DIR = BASE_DIR / "data" / "live"
READINGS_FILE = LIVE_DIR / "readings.jsonl"
USERS_FILE = LIVE_DIR / "users.json"
NOTICES_FILE = LIVE_DIR / "notices.json"
SITES_FILE = LIVE_DIR / "sites.json"
AUDIT_FILE = LIVE_DIR / "audit.jsonl"

HISTORY_HOURS = 24
SESSION_HOURS = 12
MAX_BODY_BYTES = 1_000_000
ROLES = ("admin", "planner")
SITE_STATUSES = ("active", "maintenance", "offline")
NOTICE_TYPES = ("info", "maintenance", "warning", "error")
DEVICE_KEY = os.environ.get("NMA_DEVICE_KEY", "")

lock = threading.Lock()


def now_utc():
    return datetime.now(timezone.utc)


def parse_time(value):
    try:
        t = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return t if t.tzinfo else t.replace(tzinfo=timezone.utc)
    except ValueError:
        return now_utc()


def read_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path, data):
    LIVE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)

# =========================
# ACCOUNTS
# =========================


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 200_000).hex()
    return salt, digest


def check_password(user, password):
    _, digest = hash_password(password, user["salt"])
    return hmac.compare_digest(digest, user["hash"])


def load_users():
    return read_json(USERS_FILE, {})


def cli_add_user(username, role, name):
    username = username.strip().lower()
    if not re.fullmatch(r"[a-z0-9_.-]{3,32}", username):
        sys.exit("Username must be 3-32 characters: letters, numbers, . _ or -")
    if role not in ROLES:
        sys.exit(f"Role must be one of: {', '.join(ROLES)}")
    password = getpass.getpass(f"Password for {username}: ")
    if len(password) < 8:
        sys.exit("Password must be at least 8 characters.")
    if getpass.getpass("Repeat password: ") != password:
        sys.exit("Passwords do not match.")
    users = load_users()
    salt, digest = hash_password(password)
    users[username] = {"role": role, "name": name or username, "salt": salt, "hash": digest}
    write_json(USERS_FILE, users)
    print(f"Saved {username} ({role}).")


def cli_list_users():
    users = load_users()
    if not users:
        print("No staff accounts yet.")
    for u, info in users.items():
        print(f"{u:20} {info['role']:8} {info.get('name', '')}")


def cli_remove_user(username):
    users = load_users()
    if users.pop(username.strip().lower(), None) is None:
        sys.exit("No such user.")
    write_json(USERS_FILE, users)
    print(f"Removed {username}.")

# =========================
# STATE
# =========================

readings = []          # newest last, last 24 hours
sessions = {}          # token -> {username, role, name, expires}
failed_logins = {}     # ip -> [timestamps]


def audit(user, action, detail):
    entry = {"ts": now_utc().isoformat(), "user": user or "system", "action": action, "detail": detail}
    LIVE_DIR.mkdir(parents=True, exist_ok=True)
    with AUDIT_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def load_history():
    if not READINGS_FILE.exists():
        return
    cutoff = now_utc() - timedelta(hours=HISTORY_HOURS)
    with READINGS_FILE.open(encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if parse_time(r.get("timestamp")) >= cutoff:
                readings.append(r)
    print(f"[INFO] Loaded {len(readings)} readings from {READINGS_FILE}")


def validate_reading(r):
    if not isinstance(r, dict):
        raise ValueError("each reading must be a JSON object")
    if not isinstance(r.get("site_id"), str) or not r["site_id"].strip():
        raise ValueError("site_id is required")
    try:
        db = float(r.get("laeq_db"))
    except (TypeError, ValueError):
        raise ValueError("laeq_db must be a number")
    if not 0 <= db <= 150:
        raise ValueError("laeq_db must be between 0 and 150")
    # Optional GPS position. Leave lat/lng out (or send gps_fix: false) when the module has no fix.
    if r.get("lat") is not None or r.get("lng") is not None:
        try:
            lat, lng = float(r.get("lat")), float(r.get("lng"))
        except (TypeError, ValueError):
            raise ValueError("lat and lng must both be numbers")
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            raise ValueError("lat/lng out of range")


def add_reading(r):
    r.setdefault("timestamp", now_utc().astimezone().isoformat())
    with lock:
        readings.append(r)
        LIVE_DIR.mkdir(parents=True, exist_ok=True)
        with READINGS_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(r) + "\n")
        cutoff = now_utc() - timedelta(hours=HISTORY_HOURS)
        while readings and parse_time(readings[0].get("timestamp")) < cutoff:
            readings.pop(0)


def latest_per_site():
    with lock:
        latest = {}
        for r in readings:
            latest[r["site_id"]] = r
        return list(latest.values())


def active_notices():
    now = now_utc()
    return [n for n in read_json(NOTICES_FILE, []) if not n.get("expires") or parse_time(n["expires"]) > now]

# =========================
# HTTP HANDLER
# =========================


class Handler(SimpleHTTPRequestHandler):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DASHBOARD_DIR), **kwargs)

    def end_headers(self):
        # Pages and assets must be re-checked on every load: a browser that keeps an
        # old core.js next to a new admin.html runs a mix of two versions.
        if not self.path.startswith("/api/"):
            self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    # ---- helpers ----
    def send_json(self, status, body, cookie=None, cors=False):
        data = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        if cors:
            self.send_header("Access-Control-Allow-Origin", "*")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(data)

    def read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length > MAX_BODY_BYTES:
            raise ValueError("request is too large")
        if length and "application/json" not in self.headers.get("Content-Type", ""):
            raise ValueError("send JSON with Content-Type: application/json")
        return json.loads(self.rfile.read(length) or b"null")

    def current_user(self):
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        token = cookie["nma_session"].value if "nma_session" in cookie else None
        s = sessions.get(token) if token else None
        if not s or s["expires"] < time.time():
            sessions.pop(token, None)
            return None, None
        return s, token

    def require(self, role=None):
        user, _ = self.current_user()
        if not user:
            self.send_json(401, {"error": "Please sign in."})
            return None
        if role and user["role"] != role:
            self.send_json(403, {"error": "Only administrators can do this."})
            return None
        return user

    def route(self):
        return self.path.split("?")[0].rstrip("/") or "/"

    # ---- methods ----
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Device-Key")
        self.end_headers()

    def do_GET(self):
        path = self.route()
        if path == "/api/health":
            return self.send_json(200, {"service": "noise-atlas", "accounts": bool(load_users())})
        if path == "/api/readings/latest":
            return self.send_json(200, latest_per_site(), cors=True)
        if path == "/api/readings/history":
            with lock:
                return self.send_json(200, list(readings), cors=True)
        if path == "/api/me":
            user, _ = self.current_user()
            if not user:
                return self.send_json(401, {"error": "Not signed in."})
            return self.send_json(200, {k: user[k] for k in ("username", "role", "name")})
        if path == "/api/notices":
            return self.send_json(200, active_notices())
        if path == "/api/sites":
            return self.send_json(200, read_json(SITES_FILE, []))
        if path == "/api/log":
            if not self.require():
                return
            entries = []
            if AUDIT_FILE.exists():
                entries = [json.loads(line) for line in AUDIT_FILE.read_text(encoding="utf-8").splitlines()[-300:] if line.strip()]
            return self.send_json(200, entries[::-1])
        if path.startswith("/api/"):
            return self.send_json(404, {"error": "not found"})
        if path.endswith(".py"):
            return self.send_error(404)
        return super().do_GET()

    def do_POST(self):
        path = self.route()
        try:
            body = self.read_body()
        except (ValueError, json.JSONDecodeError) as e:
            return self.send_json(400, {"error": str(e)})

        if path == "/api/readings":
            if DEVICE_KEY and not hmac.compare_digest(self.headers.get("X-Device-Key", ""), DEVICE_KEY):
                audit(None, "reading.rejected", f"Rejected readings from {self.client_address[0]}: wrong device key")
                return self.send_json(403, {"error": "wrong device key"}, cors=True)
            items = body if isinstance(body, list) else [body]
            try:
                for r in items:
                    validate_reading(r)
            except ValueError as e:
                audit(None, "reading.rejected", f"Rejected reading from {self.client_address[0]}: {e}")
                return self.send_json(400, {"error": str(e)}, cors=True)
            for r in items:
                add_reading(r)
            return self.send_json(201, {"stored": len(items)}, cors=True)

        if path == "/api/login":
            ip = self.client_address[0]
            recent = [t for t in failed_logins.get(ip, []) if t > time.time() - 600]
            if len(recent) >= 5:
                return self.send_json(429, {"error": "Too many failed attempts. Try again in 10 minutes."})
            body = body if isinstance(body, dict) else {}
            username = str(body.get("username", "")).strip().lower()
            user = load_users().get(username)
            if not user or not check_password(user, str(body.get("password", ""))):
                failed_logins[ip] = recent + [time.time()]
                audit(username or None, "login.failed", f"Failed sign-in for '{username}' from {ip}")
                return self.send_json(401, {"error": "Wrong username or password."})
            failed_logins.pop(ip, None)
            token = secrets.token_urlsafe(32)
            sessions[token] = {"username": username, "role": user["role"], "name": user.get("name", username), "expires": time.time() + SESSION_HOURS * 3600}
            audit(username, "login", f"{user.get('name', username)} signed in")
            cookie = f"nma_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={SESSION_HOURS * 3600}"
            return self.send_json(200, {"username": username, "role": user["role"], "name": user.get("name", username)}, cookie=cookie)

        if path == "/api/logout":
            user, token = self.current_user()
            if token:
                sessions.pop(token, None)
                audit(user["username"], "logout", "Signed out")
            return self.send_json(200, {"ok": True}, cookie="nma_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0")

        if path == "/api/notices":
            user = self.require("admin")
            if not user:
                return
            body = body if isinstance(body, dict) else {}
            title = str(body.get("title", "")).strip()[:120]
            if not title:
                return self.send_json(400, {"error": "A notice needs a title."})
            notice = {
                "id": "N" + secrets.token_hex(4),
                "title": title,
                "body": str(body.get("body", "")).strip()[:500],
                "type": body.get("type") if body.get("type") in NOTICE_TYPES else "info",
                "site_id": body.get("site_id") or None,
                "expires": body.get("expires") or None,
                "created": now_utc().isoformat(),
                "author": user["name"],
            }
            with lock:
                write_json(NOTICES_FILE, [notice] + read_json(NOTICES_FILE, []))
            audit(user["username"], "notice.add", f'Posted notice "{title}"')
            return self.send_json(201, notice)

        return self.send_json(404, {"error": "not found"})

    def do_PUT(self):
        path = self.route()
        m = re.fullmatch(r"/api/sites/([A-Za-z0-9_-]{1,12})", path)
        if not m:
            return self.send_json(404, {"error": "not found"})
        user = self.require("admin")
        if not user:
            return
        try:
            body = self.read_body()
            lat, lng = float(body["lat"]), float(body["lng"])
            if not (-90 <= lat <= 90 and -180 <= lng <= 180):
                raise ValueError
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            return self.send_json(400, {"error": "Send a name, latitude and longitude."})
        site = {
            "id": m.group(1),
            "name": str(body.get("name", m.group(1))).strip()[:80] or m.group(1),
            "short": str(body.get("short", "")).strip()[:20],
            "setting": str(body.get("setting", "")).strip()[:40],
            "lat": lat, "lng": lng,
            "status": body.get("status") if body.get("status") in SITE_STATUSES else "active",
            "note": str(body.get("note", "")).strip()[:200],
            "location": "fixed" if body.get("location") == "fixed" else "gps",
        }
        with lock:
            sites = [s for s in read_json(SITES_FILE, []) if s.get("id") != site["id"]]
            write_json(SITES_FILE, sites + [site])
        audit(user["username"], "site.save", f"Updated {site['id']} ({site['name']}): {site['status']}" + (f" · {site['note']}" if site["note"] else ""))
        return self.send_json(200, site)

    def do_DELETE(self):
        path = self.route()
        user = self.require("admin")
        if not user:
            return
        m = re.fullmatch(r"/api/notices/([A-Za-z0-9]{1,20})", path)
        if m:
            with lock:
                notices = read_json(NOTICES_FILE, [])
                gone = [n for n in notices if n.get("id") == m.group(1)]
                write_json(NOTICES_FILE, [n for n in notices if n.get("id") != m.group(1)])
            audit(user["username"], "notice.remove", f'Removed notice "{gone[0]["title"] if gone else m.group(1)}"')
            return self.send_json(200, {"ok": True})
        m = re.fullmatch(r"/api/sites/([A-Za-z0-9_-]{1,12})", path)
        if m:
            with lock:
                sites = [s for s in read_json(SITES_FILE, []) if s.get("id") != m.group(1)]
                write_json(SITES_FILE, sites + [{"id": m.group(1), "removed": True}])
            audit(user["username"], "site.remove", f"Removed site {m.group(1)}")
            return self.send_json(200, {"ok": True})
        return self.send_json(404, {"error": "not found"})

    def log_message(self, fmt, *args):
        if "/api/readings/latest" not in str(args[0] if args else ""):
            super().log_message(fmt, *args)

# =========================
# MAIN
# =========================


def main():
    parser = argparse.ArgumentParser(description="Serve the Manila Noise Atlas dashboard and its API.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--add-user", metavar="USERNAME")
    parser.add_argument("--role", choices=ROLES, default="admin")
    parser.add_argument("--name", default="")
    parser.add_argument("--list-users", action="store_true")
    parser.add_argument("--remove-user", metavar="USERNAME")
    args = parser.parse_args()

    if args.add_user:
        return cli_add_user(args.add_user, args.role, args.name)
    if args.list_users:
        return cli_list_users()
    if args.remove_user:
        return cli_remove_user(args.remove_user)

    load_history()
    if not load_users():
        print("[WARNING] No staff accounts yet. Create one with:")
        print("          python software/dashboard/server.py --add-user admin --role admin")
    if not DEVICE_KEY:
        print("[INFO] NMA_DEVICE_KEY is not set, so any device on the network can post readings.")
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"[INFO] Public map:      http://localhost:{args.port}/")
    print(f"[INFO] Staff dashboard: http://localhost:{args.port}/admin.html")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[INFO] Stopped.")


if __name__ == "__main__":
    main()
