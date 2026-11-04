#!/usr/bin/env python3
"""
field_record.py — Record labeled 5-second training clips in the field using
the Raspberry Pi + INMP441, triggered over SSH (e.g. from a phone hotspot)
and designed to keep running inside tmux/screen after you disconnect.

Usage:
    python3 field_record.py --class vehicular --site main_road_north --minutes 15

Run inside tmux so it survives SSH disconnect:
    tmux new -s record
    python3 field_record.py --class vehicular --site main_road_north --minutes 15
    # detach: Ctrl+B then D
    # reattach later: tmux attach -t record
"""

import argparse
import csv
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# CONFIG — check these match your system before running
# ---------------------------------------------------------------------------
# Find your INMP441's ALSA device with: arecord -l
ARECORD_DEVICE = "plughw:CARD=sndrpigooglevoi,DEV=0"         # <-- CHECK/CHANGE this for your Pi
SAMPLE_RATE = 44100                    # thesis spec: 44.1 kHz
CLIP_SECONDS = 5                       # thesis-adjusted clip duration
DATASET_ROOT = Path.home() / "thesis" / "data" / "dataset"
VALID_CLASSES = {
    "ambient", "commercial", "human", "industrial", "vehicular"
}
# ---------------------------------------------------------------------------


def try_get_gps():
    """Best-effort GPS read via gpsd. Returns (lat, lon) or (None, None).
    Never raises — recording must not stop just because GPS has no fix."""
    try:
        try:
            import gps  # python3-gps, apt-installed
        except ImportError:
            # venv can't see apt packages; fall back to the system path
            sys.path.append("/usr/lib/python3/dist-packages")
            import gps
        session = gps.gps(mode=gps.WATCH_ENABLE | gps.WATCH_NEWSTYLE)
        deadline = time.time() + 2  # don't block recording for long
        while time.time() < deadline:
            report = session.next()
            if report.get("class") == "TPV":
                lat = getattr(report, "lat", None)
                lon = getattr(report, "lon", None)
                if lat and lon:
                    return lat, lon
        return None, None
    except Exception:
        return None, None


def next_clip_number(outdir: Path, class_name: str, site: str, source: str = "real") -> int:
    """Find the next zero-padded clip index so re-running doesn't overwrite
    an earlier session's files."""
    prefix = f"{class_name}_{source}_{site}_clip_"
    existing = list(outdir.glob(f"{prefix}*.wav"))
    if not existing:
        return 1
    nums = []
    for f in existing:
        try:
            nums.append(int(f.stem.split("_")[-1]))
        except ValueError:
            continue
    return max(nums, default=0) + 1


def record_clip(outfile: Path) -> bool:
    """Record one CLIP_SECONDS-long mono WAV. Returns True on success."""
    result = subprocess.run(
        [
            "arecord",
            "-D", ARECORD_DEVICE,
            "-f", "S32_LE",
            "-r", str(SAMPLE_RATE),
            "-c", "1",                 # mono, matches INMP441 setup
            "-d", str(CLIP_SECONDS),
            str(outfile),
        ],
        capture_output=True, text=True,
    )
    if result.returncode != 0 or not outfile.exists():
        print(f"  ⚠️  arecord failed: {result.stderr.strip()}")
        return False
    return True


def main():
    parser = argparse.ArgumentParser(description="Field-record labeled training clips.")
    parser.add_argument("--class", dest="class_name", required=True,
                         choices=sorted(VALID_CLASSES),
                         help="Noise class being recorded")
    parser.add_argument("--site", required=True,
                         help="Short site label, e.g. main_road_north (no spaces)")
    parser.add_argument("--sim", action="store_true",
                        help="Audio played through speakers (names files <class>_sim_<site>_...)")
    parser.add_argument("--minutes", type=float, required=True,
                         help="How long to record for")
    args = parser.parse_args()

    class_name = args.class_name
    site = args.site.strip().lower().replace(" ", "_")
    total_seconds = args.minutes * 60
    num_clips = int(total_seconds // CLIP_SECONDS)

    outdir = DATASET_ROOT / class_name
    outdir.mkdir(parents=True, exist_ok=True)

    log_path = DATASET_ROOT / "session_log.csv"
    log_exists = log_path.exists()

    source = "sim" if args.sim else "real"
    start_num = next_clip_number(outdir, class_name, site, source)

    print(f"Recording class='{class_name}' site='{site}' for {args.minutes} min "
          f"(~{num_clips} clips of {CLIP_SECONDS}s each)")
    print(f"Output: {outdir}")
    print("Press Ctrl+C to stop early — clips recorded so far are kept.\n")

    with open(log_path, "a", newline="") as logfile:
        writer = csv.writer(logfile)
        if not log_exists:
            writer.writerow(["filename", "class", "site", "timestamp_utc", "lat", "lon"])

        recorded = 0
        try:
            for i in range(num_clips):
                clip_num = start_num + i
                filename = f"{class_name}_{source}_{site}_clip_{clip_num:03d}.wav"
                outfile = outdir / filename

                ok = record_clip(outfile)
                if not ok:
                    time.sleep(0.5)
                    continue

                lat, lon = "", ""
                timestamp = datetime.now(timezone.utc).isoformat()
                writer.writerow([filename, class_name, site, timestamp, lat, lon])
                logfile.flush()

                recorded += 1
                print(f"  [{recorded}/{num_clips}] saved {filename}"
                      f"  (lat={lat}, lon={lon})")

        except KeyboardInterrupt:
            print(f"\nStopped early. {recorded} clips recorded and kept.")
            return

    print(f"\nDone. {recorded} clips recorded to {outdir}")
    print(f"Session log updated: {log_path}")


if __name__ == "__main__":
    main()
