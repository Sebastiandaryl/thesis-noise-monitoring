"""
    python extract_chaos.py --estimate   # choose delay tau (AMI) and dimension m (FNN) on a sample of clips
    python extract_chaos.py              # data/dataset -> data/features/features_chaos.csv

"""

from pathlib import Path
from multiprocessing import Pool
import argparse
import json
import time
import warnings

import numpy as np
import pandas as pd
import librosa
import nolds
from scipy.spatial import cKDTree
from scipy.spatial.distance import pdist

warnings.filterwarnings("ignore")

BASE_DIR = Path(__file__).resolve().parents[2]
DATASET_DIR = BASE_DIR / "data" / "dataset"
OUT_CSV = BASE_DIR / "data" / "features" / "features_chaos.csv"
PARAMS_JSON = BASE_DIR / "data" / "features" / "chaos_params.json"
CLASSES = ["ambient", "commercial", "human", "industrial", "vehicular"]

SR = 8000              # Hz; keeps content below 4 kHz
WINDOW = 4000          # samples (0.5 s) taken from the middle of each clip
MAX_LAG = 40           # samples searched for the AMI minimum
MAX_DIM = 10           # largest embedding dimension tried by FNN
FNN_THRESHOLD = 0.10   # m = smallest dimension with < 10% false nearest neighbours
THEILER = 50           # samples; neighbours closer in time than this are excluded
LLE_TRAJ = 20          # steps of the divergence curve fitted for the Lyapunov exponent
HIGUCHI_KMAX = 10


def load_window(path):
    y, _ = librosa.load(path, sr=SR, mono=True)
    mid = len(y) // 2
    x = y[max(0, mid - WINDOW // 2): max(0, mid - WINDOW // 2) + WINDOW].astype(float)
    sd = x.std()
    return (x - x.mean()) / sd if sd > 0 else None


def embed(x, m, tau):
    n = len(x) - (m - 1) * tau
    return np.stack([x[i * tau: i * tau + n] for i in range(m)], axis=1)


def ami(x, max_lag=MAX_LAG, bins=32):
    """Average mutual information I(x_t; x_{t+lag}) for lag = 1..max_lag."""
    edges = np.histogram_bin_edges(x, bins)
    out = []
    for lag in range(1, max_lag + 1):
        h, _, _ = np.histogram2d(x[:-lag], x[lag:], bins=[edges, edges])
        p = h / h.sum()
        px, py = p.sum(1, keepdims=True), p.sum(0, keepdims=True)
        nz = p > 0
        out.append(float((p[nz] * np.log(p[nz] / (px @ py)[nz])).sum()))
    return np.array(out)


def first_minimum(values):
    for i in range(1, len(values) - 1):
        if values[i] < values[i - 1] and values[i] <= values[i + 1]:
            return i + 1          # values[0] is lag 1
    return int(np.argmin(values)) + 1


def fnn_fraction(x, tau, max_dim=MAX_DIM, rtol=15.0, atol=2.0):
    """Fraction of false nearest neighbours for m = 1..max_dim (Kennel et al., 1992)."""
    out = []
    for m in range(1, max_dim + 1):
        n = len(x) - m * tau
        e = embed(x, m, tau)[:n]
        dist, idx = cKDTree(e).query(e, k=2)
        d, j = dist[:, 1], idx[:, 1]
        extra = np.abs(x[np.arange(n) + m * tau] - x[j + m * tau])
        false = (extra / np.maximum(d, 1e-12) > rtol) | (np.sqrt(d ** 2 + extra ** 2) / x.std() > atol)
        out.append(float(false.mean()))
    return np.array(out)


def correlation_dimension(x, m, tau):
    """Slope of log C(r) against log r over the middle of the scaling range."""
    e = embed(x, m, tau)
    d = pdist(e)
    # drop pairs closer in time than the Theiler window
    n = len(e)
    i, j = np.triu_indices(n, 1)
    d = d[(j - i) > THEILER]
    d = d[d > 0]
    r = np.logspace(np.log10(np.percentile(d, 1)), np.log10(np.percentile(d, 20)), 12)
    c = np.array([(d < ri).mean() for ri in r])
    ok = c > 0
    return float(np.polyfit(np.log(r[ok]), np.log(c[ok]), 1)[0])


def higuchi_fd(x, kmax=HIGUCHI_KMAX):
    n = len(x)
    lk = []
    for k in range(1, kmax + 1):
        lm = []
        for m0 in range(k):
            idx = np.arange(m0, n, k)
            if len(idx) < 2:
                continue
            length = np.abs(np.diff(x[idx])).sum() * (n - 1) / ((len(idx) - 1) * k)
            lm.append(length / k)
        lk.append(np.mean(lm))
    k = np.arange(1, kmax + 1)
    return float(-np.polyfit(np.log(k), np.log(lk), 1)[0])


def chaos_features(path, m, tau):
    x = load_window(path)
    if x is None:
        return None
    return {
        "lle": float(nolds.lyap_r(x, emb_dim=m, lag=tau, min_tsep=THEILER, trajectory_len=LLE_TRAJ, fit="poly")),
        "corr_dim": correlation_dimension(x, m, tau),
        "higuchi_fd": higuchi_fd(x),
    }


_LIVE_PARAMS = None


def chaos_from_audio(y, sr):
    """Chaos metrics of a live clip already in memory, with the same window, tau and m
    as the offline analysis (chaos_params.json). Returns the dashboard's field names,
    or None for silence."""
    global _LIVE_PARAMS
    if _LIVE_PARAMS is None:
        p = json.loads(PARAMS_JSON.read_text())
        _LIVE_PARAMS = (int(p["m"]), int(p["tau"]))
    m, tau = _LIVE_PARAMS
    y = librosa.resample(np.asarray(y, dtype=float), orig_sr=sr, target_sr=SR)
    mid = len(y) // 2
    x = y[max(0, mid - WINDOW // 2): max(0, mid - WINDOW // 2) + WINDOW]
    sd = x.std()
    if len(x) < WINDOW or sd == 0:
        return None
    x = (x - x.mean()) / sd
    return {
        "lle": round(float(nolds.lyap_r(x, emb_dim=m, lag=tau, min_tsep=THEILER, trajectory_len=LLE_TRAJ, fit="poly")), 4),
        "corr_dim": round(correlation_dimension(x, m, tau), 3),
        "fractal_dim": round(higuchi_fd(x), 3),
    }


def all_clips():
    return [(c, p) for c in CLASSES for p in sorted((DATASET_DIR / c).rglob("*.wav"))]


def _estimate(job):
    _, path = job
    x = load_window(path)
    if x is None:
        return None
    tau = first_minimum(ami(x))
    f = fnn_fraction(x, tau)
    m = int(np.argmax(f < FNN_THRESHOLD)) + 1 if (f < FNN_THRESHOLD).any() else MAX_DIM
    return tau, m


def _extract(job):
    label, path = job
    try:
        feats = chaos_features(path, PARAMS["m"], PARAMS["tau"])
    except Exception as e:      # keep going; report the clip
        return None, f"{path.name}: {e}"
    if feats is None:
        return None, f"{path.name}: silent clip"
    feats.update({"label": label, "filename": path.name})
    return feats, None


PARAMS = {}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--estimate", action="store_true", help="choose tau and m on a stratified sample")
    ap.add_argument("--sample", type=int, default=30, help="clips per class for --estimate")
    ap.add_argument("--procs", type=int, default=3)
    args = ap.parse_args()

    if args.estimate:
        rng = np.random.default_rng(42)
        jobs = []
        for c in CLASSES:
            clips = [j for j in all_clips() if j[0] == c]
            jobs += [clips[i] for i in rng.choice(len(clips), min(args.sample, len(clips)), replace=False)]
        with Pool(args.procs) as pool:
            res = [r for r in pool.map(_estimate, jobs) if r]
        taus, ms = np.array(res).T
        params = {"tau": int(np.median(taus)), "m": int(np.median(ms)), "sr": SR, "window": WINDOW,
                  "theiler": THEILER, "lle_trajectory_len": LLE_TRAJ, "higuchi_kmax": HIGUCHI_KMAX,
                  "fnn_threshold": FNN_THRESHOLD, "clips_used": len(res),
                  "tau_distribution": {int(k): int(v) for k, v in zip(*np.unique(taus, return_counts=True))},
                  "m_distribution": {int(k): int(v) for k, v in zip(*np.unique(ms, return_counts=True))}}
        PARAMS_JSON.write_text(json.dumps(params, indent=2))
        print(json.dumps(params, indent=2))
    else:
        PARAMS.update(json.loads(PARAMS_JSON.read_text()))
        jobs = all_clips()
        print(f"{len(jobs)} clips, tau={PARAMS['tau']}, m={PARAMS['m']}")
        rows, t0 = [], time.time()
        with Pool(args.procs) as pool:
            for k, (row, err) in enumerate(pool.imap(_extract, jobs, chunksize=4), 1):
                if err:
                    print("skipped", err)
                else:
                    rows.append(row)
                if k % 100 == 0:
                    print(f"{k}/{len(jobs)} clips, {time.time() - t0:.0f} s", flush=True)
        pd.DataFrame(rows).to_csv(OUT_CSV, index=False)
        print(f"Saved {len(rows)} rows to {OUT_CSV}")
