"""
Section 6.9 (SO6): A-weighted level of every dataset clip, summarized per site
and compared with the WHO guideline values and the dashboard alert thresholds.

    python thesis_site_levels.py      # -> data/results/table_site_levels.csv, fig_site_levels.png

Levels use the uncalibrated INMP441 offset (dBFS + 120), the same formula as
noise_logger.py, so they are estimates. The site level is the energy average
(LAeq over all clips of the site); "peak" is the loudest 5-second clip.
"""

from pathlib import Path
import re

import numpy as np
import pandas as pd
import soundfile as sf
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from noise_logger import compute_laeq

BASE_DIR = Path(__file__).resolve().parents[2]
DATASET = BASE_DIR / "data" / "dataset"
RES = BASE_DIR / "data" / "results"
SITE_ALIASES = {"commercial/baclaran_alley2": "commercial/baclaran_alley"}
WHO_DAY, WHO_NIGHT, WARNING, CRITICAL = 55, 40, 70, 85


def site_of(filename, label):
    name = re.sub(r"_clip_\d+\.wav$", "", filename, flags=re.IGNORECASE)
    name = re.sub(rf"^{label}_(real_)?", "", name)
    return SITE_ALIASES.get(f"{label}/{name}", f"{label}/{name}")


log = pd.read_csv(DATASET / "session_log.csv")
log["hour"] = pd.to_datetime(log.timestamp_utc).dt.tz_convert("Asia/Manila").dt.hour
hour_of = dict(zip(log.filename, log.hour))

rows = []
for path in sorted(DATASET.rglob("*.wav")):
    y, sr = sf.read(path)
    label = path.parent.name
    rows.append({"site": site_of(path.name, label), "category": label, "laeq": compute_laeq(y, sr),
                 "hour": hour_of.get(path.name)})
df = pd.DataFrame(rows)

energy_mean = lambda v: 10 * np.log10(np.mean(10 ** (np.asarray(v) / 10)))
site = df.groupby("site").agg(category=("category", "first"), clips=("laeq", "size"),
                              laeq=("laeq", energy_mean), peak=("laeq", "max"), quietest=("laeq", "min"),
                              hour=("hour", "median"))
site["period"] = np.select([site.hour.isna(), site.hour.between(6, 21)], ["unknown", "day"], "night")   # WHO day 06:00-22:00
site["who_limit"] = site.period.map({"day": WHO_DAY, "night": WHO_NIGHT})
site["above_who_by"] = site.laeq - site.who_limit
site["alert"] = np.select([site.laeq >= CRITICAL, site.laeq >= WARNING], ["critical", "warning"], "none")
site = site.round(1).sort_values("laeq", ascending=False)
site.to_csv(RES / "table_site_levels.csv")
print(site.to_string())
print("\nper category (energy mean of clips):")
print(df.groupby("category").laeq.agg(energy_mean).round(1).to_string())

# Figure: site level against the WHO limit for its time of day
fig, ax = plt.subplots(figsize=(7, 8))
order = site.sort_values("laeq")
ax.barh(range(len(order)), order.laeq, color="#2a78d6", height=0.65)
ax.scatter(order.who_limit, range(len(order)), marker="|", s=160, color="#0b0b0b", zorder=3, label="WHO guideline for the time of day")
ax.axvline(WARNING, color="#e34948", ls="--", lw=1.4, label="Dashboard warning (70 dB)")
for i, (_, r) in enumerate(order.iterrows()):
    ax.text(r.laeq + 0.6, i, f"{r.laeq:.0f}", va="center", fontsize=7, color="#0b0b0b")
ax.set_yticks(range(len(order)), [f"{s}  ({p})" for s, p in zip(order.index, order.period)], fontsize=8)
ax.set_xlabel("Estimated level L_Aeq (dB(A), uncalibrated)")
ax.set_xlim(30, max(90, order.laeq.max() + 5))
ax.legend(frameon=False, fontsize=8, loc="lower right")
ax.grid(axis="x", color="#e4e3df", lw=0.8)
ax.set_axisbelow(True)
for side in ("top", "right"):
    ax.spines[side].set_visible(False)
fig.savefig(RES / "fig_site_levels.png", dpi=200, bbox_inches="tight")
print("saved")
