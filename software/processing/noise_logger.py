"""
Long-term noise logger for the forecasting experiment (SO5).

Every --interval seconds: record 5 s with the INMP441, compute the A-weighted
level (LAeq, uncalibrated: dBFS + 120 from the INMP441 datasheet), classify the
clip with the live model, and append one row to readings.csv. Clips are kept
in clips/ unless --no-audio is given. With --url, each reading is also posted
to the GIS dashboard (POST /api/readings); set NMA_DEVICE_KEY when the server
requires a device key. Clips below QUIET_DB are labelled ambient without
running the model (quiet-level rule, see live_monitor.py). Run inside tmux so it survives logout:

    tmux new -s logger
    python noise_logger.py --site home_garage --site-id N01 --url https://noisemonitoringsystem.pythonanywhere.com
    (Ctrl+B then D to detach; `tmux attach -t logger` to come back; Ctrl+C to stop)
"""

from pathlib import Path
from datetime import datetime, timezone
import argparse
from collections import deque
import csv
import json
import os
import subprocess
import urllib.request
import time
import warnings

import numpy as np
import pandas as pd
import soundfile as sf
import joblib

from extract_features import extract_features   # same features as training
from extract_yamnet import yamnet_features

warnings.filterwarnings("ignore")

BASE_DIR = Path(__file__).resolve().parents[2]
MODEL_DIR = BASE_DIR / "data" / "features"
MODEL_PATH = MODEL_DIR / "ensemble_model.joblib"
LOG_ROOT = BASE_DIR / "data" / "logging"

RECORD_SECONDS = 5   # must match the 5-second training clips
# The INMP441 gives a loud low-frequency thump for ~0.7 s each time arecord
# starts after being idle; field_record.py records clips back to back, so the
# training clips almost never have it. Record this much extra and drop it.
WARMUP_SECONDS = 1
DEVICE = "plughw:CARD=sndrpigooglevoi,DEV=0"   # same as realtime_predict_rf.py

# INMP441: -26 dBFS at 94 dB SPL, so dB SPL = dBFS + 120 (not calibrated
# against a sound level meter; same offset as publish_reading.py).
CALIBRATION_OFFSET_DB = 120.0
# Quiet-level rule: below this LAeq a clip is ambient. Near the INMP441's
# self-noise floor (~33 dB(A)) peak normalization turns faint hum into a
# steady drone that the model reads as industrial.
QUIET_DB = 40.0


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


FORECAST_WINDOW = 15   # readings (minutes) averaged for the 15-minute forecast


def energy_mean(levels):
    return float(10 * np.log10(np.mean(10 ** (np.asarray(levels) / 10))))


def recent_levels(site, max_age_min=20):
    """Last FORECAST_WINDOW levels from earlier runs of this site, if recent, so a
    restart does not have to wait 15 minutes before forecasting again."""
    runs = sorted(p for p in LOG_ROOT.glob(f"{site}_*") if "DISCARD" not in p.name and (p / "readings.csv").exists())
    if not runs:
        return []
    frames = [pd.read_csv(p / "readings.csv") for p in runs[-2:]]
    df = pd.concat(frames, ignore_index=True)
    if df.empty:
        return []
    age = (datetime.now() - pd.to_datetime(df.timestamp_local.iloc[-1])).total_seconds() / 60
    return df.laeq_db.tolist()[-FORECAST_WINDOW:] if age <= max_age_min else []


def post_reading(url, reading, timeout=10):
    """POST one reading to the dashboard. Returns an error message, or None on success."""
    headers = {"Content-Type": "application/json"}
    if os.environ.get("NMA_DEVICE_KEY"):
        headers["X-Device-Key"] = os.environ["NMA_DEVICE_KEY"]
    req = urllib.request.Request(url.rstrip("/") + "/api/readings", data=json.dumps(reading).encode(),
                                 headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return None if 200 <= res.status < 300 else f"HTTP {res.status}"
    except OSError as e:
        return str(e)


def load_model():
    loaded = joblib.load(MODEL_PATH)
    if isinstance(loaded, dict):   # ensemble: average the members' probabilities
        members = [joblib.load(MODEL_DIR / f"{m}_model.joblib") for m in loaded["members"]]
        return members, np.array(loaded["classes"])
    return [loaded], loaded.classes_


def record(path):
    """Record WARMUP_SECONDS + RECORD_SECONDS and save only the last RECORD_SECONDS."""
    raw = path.with_suffix(".raw.wav")
    subprocess.run(["arecord", "-D", DEVICE, "-f", "S32_LE", "-r", "44100", "-c", "1",
                    "-d", str(WARMUP_SECONDS + RECORD_SECONDS), str(raw)],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not raw.exists() or raw.stat().st_size < 1000:
        raise RuntimeError("arecord produced no audio (check the mic / `arecord -l`)")
    y, sr = sf.read(raw, dtype="int32")
    sf.write(path, y[WARMUP_SECONDS * sr:], sr, subtype="PCM_32")
    raw.unlink()


def main():
    parser = argparse.ArgumentParser(description="Log LAeq and noise class every N seconds.")
    parser.add_argument("--site", default="home_garage", help="name of the logging location")
    parser.add_argument("--interval", type=int, default=60, help="seconds between readings")
    parser.add_argument("--count", type=int, default=0, help="stop after N readings (0 = run until Ctrl+C)")
    parser.add_argument("--no-audio", action="store_true", help="do not keep the 5 s clips")
    parser.add_argument("--url", help="dashboard address; each reading is also posted there")
    parser.add_argument("--quiet-db", type=float, default=QUIET_DB,
                        help="clips below this dB(A) are labelled ambient without the model (0 = off)")
    parser.add_argument("--site-id", default="N01", help="node id on the dashboard (must match a site there)")
    args = parser.parse_args()

    run_dir = LOG_ROOT / f"{args.site}_{datetime.now():%Y-%m-%d_%H%M}"
    clip_dir = run_dir / "clips"
    clip_dir.mkdir(parents=True, exist_ok=True)
    csv_path = run_dir / "readings.csv"

    print("Loading model...")
    members, class_names = load_model()
    columns = (["timestamp_local", "timestamp_utc", "site", "laeq_db", "category", "confidence"]
               + [f"p_{c}" for c in class_names] + ["clip"])
    with open(csv_path, "w", newline="") as fh:
        csv.writer(fh).writerow(columns)
    print(f"Logging to {csv_path} every {args.interval} s. Ctrl+C to stop.")

    history = deque(recent_levels(args.site), maxlen=FORECAST_WINDOW)
    n = 0
    next_start = time.time()
    try:
        while args.count == 0 or n < args.count:
            now = datetime.now()
            clip = clip_dir / f"{args.site}_{now:%Y%m%d_%H%M%S}.wav"
            try:
                record(clip)
                y, sr = sf.read(clip)
                laeq = compute_laeq(y, sr)

                if laeq < args.quiet_db:
                    p = (class_names == "ambient").astype(float)
                else:
                    features = extract_features(clip)
                    features.update(yamnet_features(clip))
                    row = pd.DataFrame([features])
                    p = np.mean([m.predict_proba(row[m.feature_names_in_])[0] for m in members], axis=0)
                category = class_names[np.argmax(p)]

                with open(csv_path, "a", newline="") as fh:
                    csv.writer(fh).writerow(
                        [now.isoformat(timespec="seconds"),
                         datetime.now(timezone.utc).isoformat(timespec="seconds"),
                         args.site, round(laeq, 1), category, round(float(p.max()), 3)]
                        + [round(float(v), 3) for v in p]
                        + ["" if args.no_audio else clip.name])
                if args.no_audio:
                    clip.unlink()
                n += 1
                history.append(round(laeq, 1))
                # 15-minute forecast: energy mean of the last 15 one-minute readings
                predicted = round(energy_mean(history), 1) if len(history) == FORECAST_WINDOW else None
                sent = ""
                if args.url:
                    err = post_reading(args.url, {
                        "site_id": args.site_id,
                        "timestamp": now.astimezone().isoformat(timespec="seconds"),
                        "laeq_db": round(laeq, 1),
                        "predicted_db": predicted,
                        "category": str(category),
                        "probabilities": {str(c): round(float(v), 3) for c, v in zip(class_names, p)},
                    })
                    sent = "  sent" if err is None else f"  NOT SENT ({err})"
                fc = f"  +15 min: {predicted:.1f}" if predicted is not None else ""
                print(f"{now:%H:%M:%S}  {laeq:5.1f} dB(A)  {category:10s} ({p.max():.2f})  #{n}{fc}{sent}")
            except Exception as e:   # keep logging through a single bad reading
                print(f"{now:%H:%M:%S}  reading skipped: {e}")

            next_start += args.interval
            time.sleep(max(0, next_start - time.time()))
    except KeyboardInterrupt:
        pass
    print(f"\nStopped after {n} readings. Data: {csv_path}")


if __name__ == "__main__":
    main()
