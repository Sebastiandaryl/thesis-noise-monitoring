"""
Section 6.10: end-to-end delay from the start of a recording on the Raspberry Pi
until the reading is available from the online dashboard API.

    python measure_delay.py --n 10      # watches the next 10 readings of node N01
"""
import argparse, json, time, urllib.request
from datetime import datetime

ap = argparse.ArgumentParser()
ap.add_argument("--url", default="https://noisemonitoringsystem.pythonanywhere.com")
ap.add_argument("--site-id", default="N01")
ap.add_argument("--n", type=int, default=10)
args = ap.parse_args()

def latest():
    with urllib.request.urlopen(args.url + "/api/readings/latest", timeout=10) as r:
        rows = [x for x in json.load(r) if x.get("site_id") == args.site_id]
    return rows[0]["timestamp"] if rows else None

seen, delays, misses = latest(), [], 0
while len(delays) < args.n:
    time.sleep(0.5)
    try:
        ts = latest()
    except OSError:
        misses += 1
        continue
    if ts and ts != seen:
        seen = ts
        d = (datetime.now().astimezone() - datetime.fromisoformat(ts)).total_seconds()
        delays.append(d)
        print(f"{ts}  available after {d:.1f} s", flush=True)
print(json.dumps({"n": len(delays), "mean_s": round(sum(delays) / len(delays), 1), "min_s": round(min(delays), 1),
                  "max_s": round(max(delays), 1), "failed_polls": misses}))
