"""
Helpers for sending prototype readings to the GIS dashboard.

Usage inside realtime_predict_rf.py (after recording and classifying):

    from publish_reading import compute_laeq, send_reading

    audio = record_audio()
    laeq = compute_laeq(audio, TARGET_SR)          # use the RAW audio, before peak normalization
    ...
    send_reading(
        site_id="S01",
        laeq_db=laeq,
        category=prediction,
        probabilities=dict(zip(model.classes_, probabilities)),
    )

With a GPS module (for example a NEO-6M on the Pi's serial port), add its position.
If the module has no fix, the dashboard keeps the node at its saved location:

    from publish_reading import read_gps
    send_reading(..., gps=read_gps())

Run this file directly to send one test reading:

    python software/processing/publish_reading.py --site S01 --db 72.5
    python software/processing/publish_reading.py --site S01 --db 72.5 --lat 14.5647 --lng 120.9932
    python software/processing/publish_reading.py --site S01 --db 72.5 --no-fix
"""

import argparse
import json
import os
import time
import urllib.request
from datetime import datetime

import numpy as np

# =========================
# SETTINGS
# =========================

DASHBOARD_URL = "https://noisemonitoringsystem.pythonanywhere.com/api/readings"

# Must match NMA_DEVICE_KEY on the server when the server sets one.
DEVICE_KEY = os.environ.get("NMA_DEVICE_KEY", "")

# INMP441: -26 dBFS at 94 dB SPL, so dB SPL = dBFS + 120.
# Adjust after calibrating against a reference sound level meter.
CALIBRATION_OFFSET_DB = 120.0

# =========================
# SOUND LEVEL
# =========================


def a_weighting(freqs):
    """IEC 61672 A-weighting gain in dB for each frequency."""
    f2 = np.asarray(freqs, dtype=float) ** 2
    ra = (12194.0 ** 2 * f2 ** 2) / (
        (f2 + 20.6 ** 2)
        * np.sqrt((f2 + 107.7 ** 2) * (f2 + 737.9 ** 2))
        * (f2 + 12194.0 ** 2)
    )
    with np.errstate(divide="ignore"):
        return 20 * np.log10(ra) + 2.0


def compute_laeq(y, sr, calibration_offset=CALIBRATION_OFFSET_DB):
    """A-weighted equivalent level (LAeq) of a float audio clip in [-1, 1]."""
    y = np.asarray(y, dtype=float)
    y = y - np.mean(y)
    if not np.any(y):
        return 0.0
    spectrum = np.fft.rfft(y)
    freqs = np.fft.rfftfreq(len(y), 1.0 / sr)
    gain = np.zeros_like(freqs)
    gain[1:] = 10 ** (a_weighting(freqs[1:]) / 20)
    weighted = np.fft.irfft(spectrum * gain, n=len(y))
    rms = np.sqrt(np.mean(weighted ** 2))
    return float(20 * np.log10(max(rms, 1e-12)) + calibration_offset)

# =========================
# GPS (optional)
# =========================

GPS_PORT = "/dev/serial0"   # NEO-6M TX -> Pi RX (GPIO15); enable the serial port in raspi-config
GPS_BAUD = 9600


def _nmea_degrees(value, hemisphere):
    """Convert NMEA ddmm.mmmm / dddmm.mmmm to signed decimal degrees."""
    if not value:
        return None
    dot = value.index(".")
    degrees = float(value[:dot - 2]) + float(value[dot - 2:]) / 60
    return -degrees if hemisphere in ("S", "W") else degrees


def parse_gga(line):
    """Parse a $GPGGA/$GNGGA sentence. Returns a dict with fix, lat, lng, satellites."""
    parts = line.strip().split("*")[0].split(",")
    if len(parts) < 8 or not parts[0].endswith("GGA"):
        return None
    quality = int(parts[6] or 0)
    if quality == 0 or not parts[2] or not parts[4]:
        return {"fix": False}
    return {
        "fix": True,
        "lat": round(_nmea_degrees(parts[2], parts[3]), 6),
        "lng": round(_nmea_degrees(parts[4], parts[5]), 6),
        "satellites": int(parts[7] or 0),
    }


def read_gps(port=GPS_PORT, baud=GPS_BAUD, timeout=3.0):
    """Read one position from the GPS module. Returns {"fix": False} when there is no fix
    (indoors, no module, no pyserial), so the dashboard falls back to the saved location."""
    try:
        import serial  # pip install pyserial
    except ImportError:
        return {"fix": False}
    try:
        with serial.Serial(port, baud, timeout=1) as gps:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                line = gps.readline().decode("ascii", errors="ignore")
                fix = parse_gga(line)
                if fix is not None:
                    return fix
    except (OSError, ValueError) as e:
        print(f"[WARNING] GPS not readable on {port}: {e}")
    return {"fix": False}

# =========================
# SEND TO DASHBOARD
# =========================


def send_reading(site_id, laeq_db, predicted_db=None, category=None, probabilities=None,
                 lle=None, corr_dim=None, fractal_dim=None, gps=None, url=DASHBOARD_URL, timeout=3):
    """POST one reading to the dashboard server. Returns True on success.
    gps is the result of read_gps(), or None for nodes without a GPS module."""
    reading = {
        "site_id": site_id,
        "timestamp": datetime.now().astimezone().isoformat(),
        "laeq_db": round(float(laeq_db), 1),
        "predicted_db": None if predicted_db is None else round(float(predicted_db), 1),
        "category": category,
        "probabilities": {k: round(float(v), 3) for k, v in (probabilities or {}).items()},
        "lle": lle,
        "corr_dim": corr_dim,
        "fractal_dim": fractal_dim,
    }
    if gps is not None:
        reading["gps_fix"] = bool(gps.get("fix"))
        if gps.get("fix"):
            reading["lat"], reading["lng"] = gps["lat"], gps["lng"]
    data = json.dumps(reading).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if DEVICE_KEY:
        headers["X-Device-Key"] = DEVICE_KEY
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return 200 <= res.status < 300
    except OSError as e:
        print(f"[WARNING] Could not send reading to {url}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Send one test reading to the dashboard.")
    parser.add_argument("--site", default="S01")
    parser.add_argument("--db", type=float, default=70.0)
    parser.add_argument("--category", default="vehicular")
    parser.add_argument("--url", default=DASHBOARD_URL)
    parser.add_argument("--lat", type=float, help="test GPS latitude")
    parser.add_argument("--lng", type=float, help="test GPS longitude")
    parser.add_argument("--no-fix", action="store_true", help="send a reading whose GPS has no fix")
    parser.add_argument("--read-gps", action="store_true", help="read the real GPS module")
    args = parser.parse_args()
    gps = None
    if args.read_gps:
        gps = read_gps()
        print(f"GPS: {gps}")
    elif args.no_fix:
        gps = {"fix": False}
    elif args.lat is not None and args.lng is not None:
        gps = {"fix": True, "lat": args.lat, "lng": args.lng}
    ok = send_reading(args.site, args.db, predicted_db=args.db + 1.5, category=args.category,
                      probabilities={args.category: 0.8}, gps=gps, url=args.url)
    print("Sent." if ok else "Failed.")


if __name__ == "__main__":
    main()
