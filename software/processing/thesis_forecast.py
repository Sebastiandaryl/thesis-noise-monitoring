"""
Section 6.8 (SO5): 15-minute-ahead forecast of the A-weighted level from the
one-minute readings logged by noise_logger.py.

    python thesis_forecast.py      # all data/logging/home_garage_* runs -> data/results/

Three forecasts of the level 15 minutes ahead, each using only readings up to
the forecast time:
  persistence     the latest reading
  moving average  the energy mean of the last 15 readings
  linear model    least-squares fit of the target on the latest reading, the
                  15-minute energy mean, and the trend (slope) of the last 15
                  readings, trained on the first 60% of the log and tested on
                  the rest (time order kept, no shuffling). Time of day is not
                  used: one night of data cannot teach a daily pattern.
All three are scored on the same test period (the last 40%) with the mean
absolute error, the share of forecasts within 3 dB, and the bias.
"""

from pathlib import Path
import json

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BASE_DIR = Path(__file__).resolve().parents[2]
LOG = BASE_DIR / "data" / "logging"
RES = BASE_DIR / "data" / "results"
HORIZON = 15        # minutes ahead
WINDOW = 15         # past readings used
TRAIN_SHARE = 0.6


def energy_mean(v):
    return 10 * np.log10(np.mean(10 ** (np.asarray(v) / 10)))


runs = sorted(p for p in LOG.glob("home_garage_*") if "DISCARD" not in p.name)
df = pd.concat([pd.read_csv(p / "readings.csv") for p in runs], ignore_index=True)
df["t"] = pd.to_datetime(df.timestamp_local).dt.floor("min")
s = df.groupby("t").laeq_db.mean().asfreq("1min")          # one value per minute; gaps stay NaN
print(f"{len(df)} readings from {s.index[0]} to {s.index[-1]} ({s.notna().sum()} minutes with data)")

rows = []
for i in range(WINDOW - 1, len(s) - HORIZON):
    past = s.iloc[i - WINDOW + 1:i + 1]
    target = s.iloc[i + HORIZON]
    if past.isna().any() or np.isnan(target):
        continue
    rows.append({"time": s.index[i], "target_time": s.index[i + HORIZON], "target": target,
                 "persistence": past.iloc[-1], "moving_average": energy_mean(past),
                 "slope": np.polyfit(np.arange(WINDOW), past.values, 1)[0]})
f = pd.DataFrame(rows)
n_train = int(len(f) * TRAIN_SHARE)
train, test = f.iloc[:n_train], f.iloc[n_train:].copy()

cols = ["persistence", "moving_average", "slope"]
X = np.c_[np.ones(len(train)), train[cols]]
coef, *_ = np.linalg.lstsq(X, train.target, rcond=None)
test["linear_model"] = np.c_[np.ones(len(test)), test[cols]] @ coef

out = []
for m in ("persistence", "moving_average", "linear_model"):
    err = test[m] - test.target
    out.append({"method": m, "mae_db": abs(err).mean(), "within_3db_pct": 100 * (abs(err) <= 3).mean(),
                "bias_db": err.mean(), "max_error_db": abs(err).max()})
res = pd.DataFrame(out).round(2)
res.to_csv(RES / "table_forecast.csv", index=False)
info = {"readings": int(len(df)), "start": str(s.index[0]), "end": str(s.index[-1]),
        "hours": round((s.index[-1] - s.index[0]).total_seconds() / 3600, 1),
        "forecasts_train": int(len(train)), "forecasts_test": int(len(test)),
        "test_start": str(test.time.iloc[0]), "level_min": round(float(s.min()), 1),
        "level_max": round(float(s.max()), 1), "level_mean": round(float(energy_mean(s.dropna())), 1)}
(RES / "forecast_info.json").write_text(json.dumps(info, indent=2))
print(json.dumps(info, indent=2))
print(res.to_string(index=False))
print("linear coefficients (const, persistence, moving_average, slope):", np.round(coef, 3))

best = res.sort_values("mae_db").iloc[0].method
fig, ax = plt.subplots(figsize=(9, 3.6))
ax.plot(s.index, s.values, color="#b9b8b3", lw=1, label="Measured level (each minute)")
ax.plot(test.target_time, test[best], color="#2a78d6", lw=1.6, label=f"Forecast 15 min ahead ({best.replace('_', ' ')})")
if best != "moving_average":
    ax.plot(test.target_time, test.moving_average, color="#e07a1f", lw=1.6, label="Forecast 15 min ahead (moving average, used on the dashboard)")
ax.axvline(test.time.iloc[0] + pd.Timedelta(minutes=HORIZON), color="#52514e", ls=":", lw=1)
ax.text(test.time.iloc[0] + pd.Timedelta(minutes=HORIZON), ax.get_ylim()[1], " test period", va="top", fontsize=8, color="#52514e")
ax.set_ylabel("L_Aeq (dB(A), uncalibrated)")
ax.legend(frameon=False, fontsize=8, loc="upper left")
ax.grid(color="#e4e3df", lw=0.6)
for side in ("top", "right"):
    ax.spines[side].set_visible(False)
fig.autofmt_xdate()
fig.savefig(RES / "fig_forecast.png", dpi=200, bbox_inches="tight")
print("best:", best)
