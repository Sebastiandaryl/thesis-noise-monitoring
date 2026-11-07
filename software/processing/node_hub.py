"""
Classifier hub for phone and laptop nodes.

Phones and laptops become sensor nodes by opening node.html on the dashboard
(for example https://noisemonitoringsystem.pythonanywhere.com/node.html). Each
one records 5-second clips with its own microphone and sends them to the
dashboard. This script takes those clips, runs the SAME pipeline as the Pi
(calibrated A-weighted LAeq, quiet-level rule, handcrafted features + YAMNet,
ensemble model, 15-minute forecast, optional chaos metrics) and posts the
finished reading back to the dashboard.

Run it on the Pi (everything is already installed there) or on any laptop with
requirements.txt installed:

    python software/processing/node_hub.py --url https://noisemonitoringsystem.pythonanywhere.com
    python software/processing/node_hub.py --url ... --chaos     # also compute lambda, D2, Df per node

When the hub is not running, the dashboard still stores each node's level, just
without a noise class. Set NMA_DEVICE_KEY when the server requires a device key.
"""

from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
import argparse
import base64
import json
import os
import signal
import time
import urllib.request
import warnings

import numpy as np
import pandas as pd
import soundfile as sf

from extract_features import extract_features   # same features as training
from extract_yamnet import yamnet_features
from noise_logger import compute_laeq, load_model, energy_mean, QUIET_DB

warnings.filterwarnings("ignore")

BASE_DIR = Path(__file__).resolve().parents[2]
TEMP_WAV = BASE_DIR / "data" / "temp_hub.wav"
FORECAST_MINUTES = 15


def request(url, data=None, timeout=15):
    headers = {"Content-Type": "application/json"}
    if os.environ.get("NMA_DEVICE_KEY"):
        headers["X-Device-Key"] = os.environ["NMA_DEVICE_KEY"]
    req = urllib.request.Request(url, data=None if data is None else json.dumps(data).encode(),
                                 headers=headers, method="GET" if data is None else "POST")
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return json.loads(res.read() or b"null")


def ignore_ctrl_c():
    signal.signal(signal.SIGINT, signal.SIG_IGN)


def main():
    ap = argparse.ArgumentParser(description="Classify clips from phone/laptop nodes and post the readings.")
    ap.add_argument("--url", required=True, help="dashboard address, e.g. https://noisemonitoringsystem.pythonanywhere.com")
    ap.add_argument("--quiet-db", type=float, default=QUIET_DB,
                    help="clips below this dB(A) are labelled ambient without the model (0 = off)")
    ap.add_argument("--chaos", action="store_true", help="also compute the chaos metrics (uses more CPU)")
    args = ap.parse_args()
    base = args.url.rstrip("/")

    chaos_pool, chaos_jobs, chaos_latest = None, {}, {}
    if args.chaos:
        from extract_chaos import chaos_from_audio
        chaos_pool = ProcessPoolExecutor(max_workers=1, initializer=ignore_ctrl_c)

    print("Loading model...")
    members, class_names = load_model()
    TEMP_WAV.parent.mkdir(parents=True, exist_ok=True)
    recent = {}                        # site_id -> [(time, laeq)] of the last 15 minutes
    print(f"Hub running: waiting for clips from phone/laptop nodes at {base}. Ctrl+C to stop.")
    waiting_msg = 0.0
    try:
        while True:
            try:
                clip = request(base + "/api/clips/next")["clip"]
            except Exception as e:
                print(f"{datetime.now():%H:%M:%S}  dashboard not reachable: {e}")
                time.sleep(5)
                continue
            if not clip:
                if time.time() - waiting_msg > 60:
                    print(f"{datetime.now():%H:%M:%S}  waiting for clips (open node.html on a phone or laptop)")
                    waiting_msg = time.time()
                time.sleep(1)
                continue

            t0 = time.time()
            site, sr = clip["site_id"], int(clip["sr"])
            samples = np.frombuffer(base64.b64decode(clip.pop("audio")), dtype="<i2")
            y = samples.astype(np.float64) / 32768.0
            offset = float(clip.get("cal_offset", 0) or 0)
            laeq = compute_laeq(y, sr, offset) if offset else float(clip["laeq_db"])
            if laeq < args.quiet_db:
                p = (class_names == "ambient").astype(float)
            else:
                sf.write(TEMP_WAV, samples, sr, subtype="PCM_16")
                feats = extract_features(TEMP_WAV)
                feats.update(yamnet_features(TEMP_WAV))
                row = pd.DataFrame([feats])
                p = np.mean([m.predict_proba(row[m.feature_names_in_])[0] for m in members], axis=0)
            category = str(class_names[np.argmax(p)])

            # 15-minute forecast per node, same as live_monitor.py
            now = time.time()
            hist = [(t, v) for t, v in recent.get(site, []) if now - t <= FORECAST_MINUTES * 60] + [(now, laeq)]
            recent[site] = hist
            predicted = round(energy_mean([v for _, v in hist]), 1) if now - hist[0][0] >= 60 else None

            if chaos_pool:
                job = chaos_jobs.get(site)
                if job is not None and job.done():
                    try:
                        chaos_latest[site] = job.result() or chaos_latest.get(site, {})
                    except Exception:
                        pass
                    job = None
                if job is None:
                    chaos_jobs[site] = chaos_pool.submit(chaos_from_audio, y, sr)

            reading = {k: v for k, v in clip.items() if k != "sr"}
            reading.update({"laeq_db": round(laeq, 1), "category": category, "predicted_db": predicted,
                            "probabilities": {str(c): round(float(v), 3) for c, v in zip(class_names, p)},
                            **chaos_latest.get(site, {})})
            try:
                request(base + "/api/readings", reading)
                sent = "sent"
            except Exception as e:
                sent = f"NOT SENT ({e})"
            print(f"{datetime.now():%H:%M:%S}  {site:6s} {clip.get('name', '')[:18]:18s} {laeq:5.1f} dB(A)  "
                  f"{category:10s} ({p.max():.2f})  [{time.time() - t0:.1f} s]  {sent}")
    except KeyboardInterrupt:
        pass
    finally:
        if chaos_pool:
            chaos_pool.shutdown(wait=False, cancel_futures=True)


if __name__ == "__main__":
    main()
