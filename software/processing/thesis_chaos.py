"""
Sections 6.4 and 6.5: chaos metrics per category (SO3) and classification with
and without the chaos features on the same leave-one-site-out folds (SO1).

    python thesis_chaos.py      # needs features_chaos.csv (extract_chaos.py) -> data/results/
"""

from pathlib import Path
import json
import re
import time

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.stats import wilcoxon, kruskal
from sklearn.model_selection import LeaveOneGroupOut, cross_val_predict
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score

from extract_chaos import load_window, embed

BASE_DIR = Path(__file__).resolve().parents[2]
FEAT = BASE_DIR / "data" / "features"
RES = BASE_DIR / "data" / "results"
CHAOS = ["lle", "corr_dim", "higuchi_fd"]
NAMES = {"lle": "Largest Lyapunov exponent", "corr_dim": "Correlation dimension", "higuchi_fd": "Higuchi fractal dimension"}
SITE_ALIASES = {"commercial/baclaran_alley2": "commercial/baclaran_alley"}
INK, INK2, GRID, BLUE = "#0b0b0b", "#52514e", "#e4e3df", "#2a78d6"
plt.rcParams.update({"font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2,
                     "ytick.color": INK2, "axes.spines.top": False, "axes.spines.right": False,
                     "savefig.dpi": 200, "savefig.bbox": "tight"})


def site_of(filename, label):
    name = re.sub(r"_clip_\d+\.wav$", "", filename, flags=re.IGNORECASE)
    name = re.sub(rf"^{label}_(real_)?", "", name)
    return SITE_ALIASES.get(f"{label}/{name}", f"{label}/{name}")


hand = pd.read_csv(FEAT / "features.csv").drop(columns=["filepath"])
HAND = [c for c in hand.columns if c not in ("label", "filename")]
yam = pd.read_csv(FEAT / "features_yamnet.csv").drop(columns=["label"])
YAM = [c for c in yam.columns if c != "filename"]
chaos = pd.read_csv(FEAT / "features_chaos.csv").drop(columns=["label"])
df = hand.merge(yam, on="filename").merge(chaos, on="filename")
df = df[np.isfinite(df[CHAOS]).all(axis=1)].reset_index(drop=True)
y = df["label"].values
groups = np.array([site_of(f, l) for f, l in zip(df["filename"], df["label"])])
labels = sorted(set(y))
params = json.loads((FEAT / "chaos_params.json").read_text())
print(f"{len(df)} clips with chaos features; tau={params['tau']}, m={params['m']}")

# ---------- 6.4: metrics per category ----------
stats = df.groupby("label")[CHAOS].agg(["mean", "std"]).round(3)
stats.to_csv(RES / "table_chaos_per_class.csv")
kw = {c: kruskal(*[df.loc[df.label == l, c] for l in labels]) for c in CHAOS}
pd.DataFrame({c: {"H": round(k.statistic, 1), "p": k.pvalue} for c, k in kw.items()}).T.to_csv(RES / "table_chaos_kruskal.csv")
print(stats, "\n", {c: (round(k.statistic, 1), f"{k.pvalue:.2e}") for c, k in kw.items()})

fig, axes = plt.subplots(1, 3, figsize=(12, 3.8))
for ax, c in zip(axes, CHAOS):
    data = [df.loc[df.label == l, c].values for l in labels]
    bp = ax.boxplot(data, patch_artist=True, widths=0.55, showfliers=False,
                    medianprops={"color": INK, "lw": 1.5}, whiskerprops={"color": INK2}, capprops={"color": INK2})
    for b in bp["boxes"]:
        b.set(facecolor=BLUE, alpha=0.35, edgecolor=BLUE)
    ax.set_xticks(range(1, len(labels) + 1), [l.capitalize() for l in labels], rotation=30, ha="right")
    ax.set_title(NAMES[c], fontsize=10, color=INK)
    ax.grid(axis="y", color=GRID, lw=0.6)
    ax.set_axisbelow(True)
fig.tight_layout()
fig.savefig(RES / "fig_chaos_boxplots.png")
plt.close(fig)

# Phase-space portraits (x(t) against x(t + tau)) of two contrasting categories
fig, axes = plt.subplots(1, 2, figsize=(9, 4.3), sharex=True, sharey=True)
for ax, cls in zip(axes, ("ambient", "vehicular")):
    row = df[df.label == cls].iloc[len(df[df.label == cls]) // 2]
    path = next((BASE_DIR / "data" / "dataset" / cls).rglob(row["filename"]))
    e = embed(load_window(path), 2, params["tau"])
    ax.plot(e[:, 0], e[:, 1], color=BLUE, lw=0.4, alpha=0.8)
    ax.set_title(f"{cls.capitalize()} (λ = {row.lle:.3f}, D₂ = {row.corr_dim:.2f})", fontsize=10, color=INK)
    ax.set_xlabel("x(t)")
    ax.grid(color=GRID, lw=0.5)
axes[0].set_ylabel(f"x(t + τ), τ = {params['tau']} samples")
fig.tight_layout()
fig.savefig(RES / "fig_phase_space.png")
plt.close(fig)

# ---------- 6.5: with and without chaos features ----------
svm = lambda: make_pipeline(StandardScaler(), SVC(C=10, class_weight="balanced", probability=True, random_state=42))
rf = lambda: RandomForestClassifier(n_estimators=200, random_state=42, n_jobs=2)
lr = lambda: make_pipeline(StandardScaler(), LogisticRegression(C=0.1, max_iter=3000, class_weight="balanced"))
cv = LeaveOneGroupOut()


def loso(make, cols, name):
    t = time.time()
    p = cross_val_predict(make(), df[cols], y, groups=groups, cv=cv, method="predict_proba")
    print(f"  {name}: {time.time() - t:.0f} s")
    return p


P = {
    "rf": loso(rf, HAND, "RF"), "rf+chaos": loso(rf, HAND + CHAOS, "RF + chaos"),
    "svm": loso(svm, HAND, "SVM"), "svm+chaos": loso(svm, HAND + CHAOS, "SVM + chaos"),
    "yamnet": loso(lr, YAM, "YAMNet"), "yamnet+chaos": loso(lr, YAM + CHAOS, "YAMNet + chaos"),
    "chaos only": loso(svm, CHAOS, "chaos only (SVM)"),
}
P["ensemble"] = P["svm"] + P["yamnet"]
P["ensemble+chaos"] = P["svm+chaos"] + P["yamnet+chaos"]


def evaluate(p):
    pred = np.array(labels)[p.argmax(1)]
    site = pd.Series(pred == y).groupby(groups).mean()
    return pred, site


rows = []
for base in ("rf", "svm", "yamnet", "ensemble"):
    pa, sa = evaluate(P[base])
    pb, sb = evaluate(P[base + "+chaos"])
    diff = sb - sa
    try:
        w = wilcoxon(sb, sa, zero_method="wilcox")
        stat, pval = w.statistic, w.pvalue
    except ValueError:                     # all differences zero
        stat, pval = np.nan, 1.0
    rows.append({"model": base, "acc_without": accuracy_score(y, pa), "acc_with": accuracy_score(y, pb),
                 "macro_f1_without": f1_score(y, pa, average="macro"), "macro_f1_with": f1_score(y, pb, average="macro"),
                 "sites_better": int((diff > 0).sum()), "sites_worse": int((diff < 0).sum()), "sites_same": int((diff == 0).sum()),
                 "wilcoxon_W": stat, "wilcoxon_p": pval})
    # per-class recall change
    for l in labels:
        m = y == l
        rows[-1][f"recall_{l}_without"] = float((pa[m] == l).mean())
        rows[-1][f"recall_{l}_with"] = float((pb[m] == l).mean())
comp = pd.DataFrame(rows).round(4)
comp.to_csv(RES / "table_chaos_comparison.csv", index=False)
pc, _ = evaluate(P["chaos only"])
print(comp[["model", "acc_without", "acc_with", "macro_f1_without", "macro_f1_with",
            "sites_better", "sites_worse", "sites_same", "wilcoxon_p"]].to_string())
print(f"chaos features alone (SVM): accuracy {accuracy_score(y, pc):.3f}, macro F1 {f1_score(y, pc, average='macro'):.3f}")
(RES / "chaos_only.json").write_text(json.dumps({"accuracy": accuracy_score(y, pc), "macro_f1": f1_score(y, pc, average="macro")}))

# Extraction time per clip for the chaos features
from extract_chaos import chaos_features
sample = df.sample(10, random_state=0)
t = time.time()
for _, r in sample.iterrows():
    chaos_features(next((BASE_DIR / "data" / "dataset" / r.label).rglob(r.filename)), params["m"], params["tau"])
print(f"chaos feature time per clip: {(time.time() - t) / 10:.2f} s")
