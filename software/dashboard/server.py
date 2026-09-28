"""
Dashboard server for the GIS noise dashboard.

Runs on the central Raspberry Pi (or any laptop) with only the Python
standard library:

    python software/dashboard/server.py            # http://localhost:8000
    python software/dashboard/server.py --port 8080

Endpoints
    GET  /                          the dashboard (index.html)
    GET  /api/readings/latest       newest reading per site (the dashboard polls this)
    GET  /api/readings/history      readings from the last 24 hours
    POST /api/readings              add one reading (JSON object) or several (JSON list)

Readings are appended to data/live/readings.jsonl so history survives a restart.
"""

from pathlib import Path
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from datetime import datetime, timedelta, timezone
import argparse
import json
import threading

# =========================
# PATH SETUP
# =========================

BASE_DIR = Path(__file__).resolve().parents[2]
DASHBOARD_DIR = Path(__file__).resolve().parent
LIVE_DIR = BASE_DIR / "data" / "live"
READINGS_FILE = LIVE_DIR / "readings.jsonl"

HISTORY_HOURS = 24
REQUIRED_FIELDS = {"site_id", "laeq_db"}

# =========================
# STORAGE
# =========================

lock = threading.Lock()
readings = []   # newest last


def parse_time(value):
    try:
        t = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return t if t.tzinfo else t.replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime.now(timezone.utc)


def load_history():
    if not READINGS_FILE.exists():
        return
    cutoff = datetime.now(timezone.utc) - timedelta(hours=HISTORY_HOURS)
    with READINGS_FILE.open(encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if parse_time(r.get("timestamp")) >= cutoff:
                readings.append(r)
    print(f"[INFO] Loaded {len(readings)} readings from {READINGS_FILE}")


def add_reading(r):
    missing = REQUIRED_FIELDS - r.keys()
    if missing:
        raise ValueError(f"missing field(s): {', '.join(sorted(missing))}")
    r.setdefault("timestamp", datetime.now(timezone.utc).astimezone().isoformat())
    with lock:
        readings.append(r)
        LIVE_DIR.mkdir(parents=True, exist_ok=True)
        with READINGS_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(r) + "\n")
        cutoff = datetime.now(timezone.utc) - timedelta(hours=HISTORY_HOURS)
        while readings and parse_time(readings[0].get("timestamp")) < cutoff:
            readings.pop(0)


def latest_per_site():
    with lock:
        latest = {}
        for r in readings:
            latest[r["site_id"]] = r
        return list(latest.values())


def history():
    with lock:
        return list(readings)

# =========================
# HTTP HANDLER
# =========================


class Handler(SimpleHTTPRequestHandler):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DASHBOARD_DIR), **kwargs)

    def send_json(self, status, body):
        data = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/")
        if path == "/api/readings/latest":
            return self.send_json(200, latest_per_site())
        if path == "/api/readings/history":
            return self.send_json(200, history())
        return super().do_GET()

    def do_POST(self):
        if self.path.split("?")[0].rstrip("/") != "/api/readings":
            return self.send_json(404, {"error": "not found"})
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"null")
            items = body if isinstance(body, list) else [body]
            for r in items:
                if not isinstance(r, dict):
                    raise ValueError("each reading must be a JSON object")
                add_reading(r)
        except (ValueError, json.JSONDecodeError) as e:
            return self.send_json(400, {"error": str(e)})
        return self.send_json(201, {"stored": len(items)})

    def log_message(self, fmt, *args):
        if "/api/readings/latest" not in (args[0] if args else ""):
            super().log_message(fmt, *args)

# =========================
# MAIN
# =========================


def main():
    parser = argparse.ArgumentParser(description="Serve the GIS noise dashboard and its readings API.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    load_history()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"[INFO] Dashboard: http://localhost:{args.port}/")
    print(f"[INFO] Readings API: http://localhost:{args.port}/api/readings/latest")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[INFO] Stopped.")


if __name__ == "__main__":
    main()
