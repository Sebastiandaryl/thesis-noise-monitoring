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

Run this file directly to send one test reading:

    python software/processing/publish_reading.py --site S01 --db 72.5
"""

import argparse
import json
import os
import urllib.request
from datetime import datetime

import numpy as np

# =========================
# SETTINGS
# =========================

DASHBOARD_URL = "http://localhost:8000/api/readings"

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
# SEND TO DASHBOARD
# =========================


def send_reading(site_id, laeq_db, predicted_db=None, category=None, probabilities=None,
                 lle=None, corr_dim=None, fractal_dim=None, url=DASHBOARD_URL, timeout=3):
    """POST one reading to the dashboard server. Returns True on success."""
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
    args = parser.parse_args()
    ok = send_reading(args.site, args.db, predicted_db=args.db + 1.5, category=args.category,
                      probabilities={args.category: 0.8}, url=args.url)
    print("Sent." if ok else "Failed.")


if __name__ == "__main__":
    main()
