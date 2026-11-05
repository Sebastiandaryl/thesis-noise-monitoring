"""
Live mode for demonstrations: records continuously and classifies every
5-second clip as it arrives, with the A-weighted level and the GPS position,
and posts each reading to the GIS dashboard.

    python live_monitor.py --site-id N02 --url https://noisemonitoringsystem.pythonanywhere.com
    python live_monitor.py --site-id N02 --url ... --save   # also keep the clips in data/live_clips/
    python live_monitor.py --trial human --setup hood   # live trial: logs setup, expected and predicted to data/results/live_trials.csv

Recording is continuous (one arecord process), so the INMP441 start-up thump
only affects the first second, which is dropped. Clips quieter than
QUIET_DB (default 40 dB(A)) are labelled ambient without running the model:
near the mic's self-noise floor (~33 dB(A)) peak normalization turns a faint
room hum into a steady drone that the model reads as industrial. Each reading takes about 1 s
to process on a Raspberry Pi 4, so a new reading arrives every 5 s.

Forecast: each reading carries the energy mean of the last 15 minutes of levels, the
same moving-average forecast as noise_logger.py (a shorter window until the node has
run for 15 minutes, none in the first minute).

Chaos: the Lyapunov exponent, D2 and Higuchi Df of the newest clip are computed in a
separate process with the settings of the offline analysis, for the staff dashboard
only. They do not feed the classifier and never hold up a reading; each reading
carries the latest finished result. --no-chaos turns this off, and trials never use it.

GPS: read from gpsd (the NEO-6M on /dev/serial0). Readings carry gps_fix and,
when there is a fix, lat/lng; the dashboard moves a node whose location is set
to GPS and keeps it at its saved position when there is no fix. Indoors the
NEO-6M often has no fix; give it a view of the sky for a few minutes first.
"""

from pathlib import Path
from datetime import datetime
import argparse
from concurrent.futures import ProcessPoolExecutor
import json
import queue
import signal
import socket
import subprocess
import threading
import time
import urllib.request
import warnings
import os

import numpy as np
import pandas as pd
import soundfile as sf

from extract_features import extract_features   # same features as training
from extract_yamnet import yamnet_features
from extract_chaos import chaos_from_audio       # same chaos settings as the offline analysis
from noise_logger import compute_laeq, load_model, energy_mean, DEVICE, WARMUP_SECONDS, QUIET_DB

warnings.filterwarnings("ignore")

BASE_DIR = Path(__file__).resolve().parents[2]
SR = 44100
CLIP_SECONDS = 5
BYTES_PER_CLIP = SR * CLIP_SECONDS * 4            # S32_LE mono
TEMP_WAV = BASE_DIR / "data" / "temp_live.wav"
CLIP_DIR = BASE_DIR / "data" / "live_clips"
TRIALS_CSV = BASE_DIR / "data" / "results" / "live_trials.csv"


class GpsReader(threading.Thread):
    """Keeps the latest fix from gpsd (TCP 2947). fix() returns (lat, lng) or None."""

    def __init__(self, max_age=10):
        super().__init__(daemon=True)
        self.latest, self.time, self.max_age = None, 0.0, max_age
        self.status = "no gpsd"

    def run(self):
        while True:
            try:
                with socket.create_connection(("127.0.0.1", 2947), timeout=10) as s:
                    s.sendall(b'?WATCH={"enable":true,"json":true}\n')
                    self.status = "no fix"
                    buf = b""
                    while True:
                        try:
                            data = s.recv(4096)
                        except socket.timeout:      # gpsd is quiet while the module sends nothing
                            continue
                        if not data:
                            break
                        buf += data
                        while b"\n" in buf:
                            line, buf = buf.split(b"\n", 1)
                            try:
                                msg = json.loads(line)
                            except ValueError:
                                continue
                            if msg.get("class") == "TPV" and msg.get("mode", 0) >= 2 and "lat" in msg:
                                self.latest, self.time = (msg["lat"], msg["lon"]), time.time()
            except OSError:
                self.status = "no gpsd"
            time.sleep(5)

    def fix(self):
        if self.latest and time.time() - self.time < self.max_age:
            return self.latest
        return None


FORECAST_MINUTES = 15


def ignore_ctrl_c():
    signal.signal(signal.SIGINT, signal.SIG_IGN)


class ChaosWorker:
    """Computes the chaos metrics of the newest clip in a separate process, on another
    of the Pi's cores. Clips that arrive while it is busy are skipped for chaos only."""

    def __init__(self):
        self.pool = ProcessPoolExecutor(max_workers=1, initializer=ignore_ctrl_c)
        self.job = self.pool.submit(int)            # start the process before any thread exists
        self.latest = {}

    def submit(self, y):
        try:
            if self.job is not None and self.job.done():
                job, self.job = self.job, None
                self.latest = job.result() or self.latest
            if self.job is None:
                self.job = self.pool.submit(chaos_from_audio, y, SR)
        except Exception as e:                      # readings carry on without chaos
            print(f"          chaos skipped: {e}")


def post_reading(url, reading, timeout=10):
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


def main():
    ap = argparse.ArgumentParser(description="Continuous live classification with GPS, posted to the dashboard.")
    ap.add_argument("--site-id", default="N02", help="node id on the dashboard")
    ap.add_argument("--url", help="dashboard address; leave out to only print")
    ap.add_argument("--save", action="store_true", help="keep each 5 s clip in data/live_clips/")
    ap.add_argument("--trial", choices=["ambient", "commercial", "human", "industrial", "vehicular"],
                    help="live trial: the true class of the sound being made; each reading is logged to "
                         "data/results/live_trials.csv and the clip is kept")
    ap.add_argument("--setup", default="",
                    help="trial condition written to the trials CSV and clip names, e.g. hood or nohood")
    ap.add_argument("--quiet-db", type=float, default=QUIET_DB,
                    help="clips below this dB(A) are labelled ambient without the model (0 = off)")
    ap.add_argument("--no-chaos", action="store_true", help="do not compute the chaos metrics")
    ap.add_argument("--gps-decimals", type=int, default=6,
                    help="decimals of lat/lng sent to the dashboard (3 = about 100 m, for testing at home)")
    args = ap.parse_args()
    args.setup = "".join(ch for ch in args.setup if ch.isalnum() or ch in "-_")

    chaos = None if args.no_chaos or args.trial else ChaosWorker()
    print("Loading model...")
    members, class_names = load_model()
    gps = GpsReader()
    gps.start()
    recent = []                                     # (time, laeq) of the last FORECAST_MINUTES
    args.save = args.save or bool(args.trial)
    if args.trial and not TRIALS_CSV.exists():
        TRIALS_CSV.write_text("time,setup,expected,predicted,confidence,laeq_db,clip\n")
    if args.save:
        CLIP_DIR.mkdir(parents=True, exist_ok=True)

    clips = queue.Queue(maxsize=3)      # the recorder never waits for the classifier
    sender = queue.Queue()

    def send_loop():
        while True:
            reading = sender.get()
            err = post_reading(args.url, reading)
            if err:
                print(f"          not sent: {err}")

    if args.url:
        threading.Thread(target=send_loop, daemon=True).start()

    rec = subprocess.Popen(["arecord", "-D", DEVICE, "-f", "S32_LE", "-r", str(SR), "-c", "1", "-t", "raw", "-q"],
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    def read_loop():
        rec.stdout.read(SR * WARMUP_SECONDS * 4)            # drop the start-up thump
        while True:
            raw = rec.stdout.read(BYTES_PER_CLIP)
            if len(raw) < BYTES_PER_CLIP:
                clips.put(None)
                return
            if clips.full():                                # classifier behind: drop the oldest clip
                clips.get_nowait()
            clips.put((datetime.now().astimezone(), np.frombuffer(raw, dtype="<i4")))

    threading.Thread(target=read_loop, daemon=True).start()
    print(f"Live: a reading every {CLIP_SECONDS} s as node {args.site_id}"
          + (f", sending to {args.url}" if args.url else "") + ". Ctrl+C to stop.")
    try:
        while True:
            item = clips.get()
            if item is None:
                print("Recording stopped (check the mic with `arecord -l`).")
                break
            t_end, samples = item
            t0 = time.time()
            y = samples.astype(np.float64) / 2 ** 31
            sf.write(TEMP_WAV, samples, SR, subtype="PCM_32")
            tag = "_".join(filter(None, [args.setup, args.trial])) if args.trial else "live"
            clip_path = CLIP_DIR / f"{tag}_{t_end:%Y%m%d_%H%M%S}.wav"
            if args.save:
                sf.write(clip_path, samples, SR, subtype="PCM_32")
            laeq = compute_laeq(y, SR)
            quiet = laeq < args.quiet_db
            if quiet:
                p = (class_names == "ambient").astype(float)
            else:
                feats = extract_features(TEMP_WAV)
                feats.update(yamnet_features(TEMP_WAV))
                row = pd.DataFrame([feats])
                p = np.mean([m.predict_proba(row[m.feature_names_in_])[0] for m in members], axis=0)
            category = str(class_names[np.argmax(p)])
            if chaos:
                chaos.submit(y)
            # 15-minute forecast, as in noise_logger.py: energy mean of the last 15 minutes
            recent.append((t_end, laeq))
            recent = [(t, v) for t, v in recent if (t_end - t).total_seconds() <= FORECAST_MINUTES * 60]
            span = (t_end - recent[0][0]).total_seconds()
            predicted = round(energy_mean([v for _, v in recent]), 1) if span >= 60 else None
            metrics = chaos.latest if chaos else {}
            fix = gps.fix()
            reading = {"site_id": args.site_id, "timestamp": t_end.isoformat(timespec="seconds"),
                       "laeq_db": round(laeq, 1), "category": category,
                       "probabilities": {str(c): round(float(v), 3) for c, v in zip(class_names, p)},
                       "predicted_db": predicted, "gps_fix": fix is not None, **metrics}
            if fix:
                reading["lat"], reading["lng"] = round(fix[0], args.gps_decimals), round(fix[1], args.gps_decimals)
            if args.url:
                sender.put(reading)
            where = f"{fix[0]:.5f}, {fix[1]:.5f}" if fix else gps.status
            print(f"{t_end:%H:%M:%S}  {laeq:5.1f} dB(A)  {category:10s} ({'quiet' if quiet else f'{p.max():.2f}'})  GPS: {where}  "
                  f"[{time.time() - t0:.1f} s]"
                  + (f"  +15 min: {predicted:.1f}" if predicted is not None else "")
                  + (f"  lambda {metrics['lle']:.3f}  D2 {metrics['corr_dim']:.2f}  Df {metrics['fractal_dim']:.2f}" if metrics else ""))
            if args.trial:
                with open(TRIALS_CSV, "a") as fh:
                    fh.write(f"{t_end.isoformat(timespec='seconds')},{args.setup},{args.trial},{category},"
                             f"{p.max():.3f},{laeq:.1f},{clip_path.name}\n")
                rows = pd.read_csv(TRIALS_CSV, keep_default_na=False)
                rows = rows[(rows.expected == args.trial) & (rows.setup == args.setup)]
                print(f"          trial {args.trial} ({args.setup or 'no setup'}): "
                      f"{(rows.predicted == rows.expected).sum()}/{len(rows)} correct")
    except KeyboardInterrupt:
        pass
    finally:
        rec.terminate()
        if chaos:
            chaos.pool.shutdown(wait=False, cancel_futures=True)


if __name__ == "__main__":
    main()
