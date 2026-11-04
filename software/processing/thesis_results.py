"""
Chapter 6 numbers from the frozen dataset: leave-one-site-out predictions of all
models, every metric the thesis reports, and the tables as CSV files.

    python thesis_results.py      # -> data/results/

Uses the same models and site grouping as train_rf.py. The LOSO class
probabilities are saved (loso_probas.npz) so the figures script does not
recompute them.
"""

from pathlib import Path
import re

import numpy as np
import pandas as pd

from sklearn.model_selection import train_test_split, LeaveOneGroupOut, cross_val_predict
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, balanced_accuracy_score, precision_recall_fscore_support,
                             roc_auc_score, confusion_matrix, f1_score)

BASE_DIR = Path(__file__).resolve().parents[2]
FEATURES_DIR = BASE_DIR / "data" / "features"
OUT = BASE_DIR / "data" / "results"
OUT.mkdir(parents=True, exist_ok=True)

SITE_ALIASES = {"commercial/baclaran_alley2": "commercial/baclaran_alley"}


def site_of(filename, label):
    name = re.sub(r"_clip_\d+\.wav$", "", filename, flags=re.IGNORECASE)
    name = re.sub(rf"^{label}_(real_)?", "", name)
    site = f"{label}/{name}"
    return SITE_ALIASES.get(site, site)


df = pd.read_csv(FEATURES_DIR / "features.csv").drop(columns=["filepath"])
HAND = [c for c in df.columns if c not in ("label", "filename")]
yam = pd.read_csv(FEATURES_DIR / "features_yamnet.csv").drop(columns=["label"])
YAM = [c for c in yam.columns if c != "filename"]
df = df.merge(yam, on="filename")
y = df["label"].values
groups = np.array([site_of(f, l) for f, l in zip(df["filename"], df["label"])])
labels = sorted(set(y))

MODELS = {
    "Random Forest": (HAND, lambda: RandomForestClassifier(n_estimators=200, random_state=42, n_jobs=2)),
    "SVM": (HAND, lambda: make_pipeline(StandardScaler(),
                                        SVC(C=10, class_weight="balanced", probability=True, random_state=42))),
    "YAMNet CNN + LR": (YAM, lambda: make_pipeline(StandardScaler(),
                                                    LogisticRegression(C=0.1, max_iter=3000, class_weight="balanced"))),
}

# ---------- dataset summary ----------
sites = pd.DataFrame({"class": y, "site": groups})
summary = sites.groupby("class").agg(clips=("site", "size"), sites=("site", "nunique"))
summary["minutes"] = (summary["clips"] * 5 / 60).round(1)
summary["share_%"] = (100 * summary["clips"] / len(df)).round(1)
summary.loc["Total"] = [len(df), sites["site"].nunique(), round(len(df) * 5 / 60, 1), 100.0]
summary.to_csv(OUT / "table_dataset_summary.csv")
sites.groupby(["class", "site"]).size().rename("clips").to_csv(OUT / "table_clips_per_site.csv")
print(summary, "\n")

# ---------- leave-one-site-out probabilities ----------
probas = {}
for name, (cols, make) in MODELS.items():
    print("LOSO:", name)
    probas[name] = cross_val_predict(make(), df[cols], y, groups=groups,
                                     cv=LeaveOneGroupOut(), method="predict_proba")
probas["Ensemble (SVM + YAMNet)"] = (probas["SVM"] + probas["YAMNet CNN + LR"]) / 2
np.savez(OUT / "loso_probas.npz", labels=labels, y=y, groups=groups,
         **{k.replace(" ", "_"): v for k, v in probas.items()})

# ---------- model comparison ----------
rows, per_class, per_site = [], [], {}
for name, p in probas.items():
    pred = np.array(labels)[p.argmax(1)]
    pr, rc, f1, _ = precision_recall_fscore_support(y, pred, labels=labels, average="macro", zero_division=0)
    rows.append({"model": name,
                 "accuracy": accuracy_score(y, pred),
                 "balanced_accuracy": balanced_accuracy_score(y, pred),
                 "macro_precision": pr, "macro_recall": rc, "macro_f1": f1,
                 "roc_auc_macro_ovr": roc_auc_score(y, p, labels=labels, multi_class="ovr", average="macro")})
    P, R, F, S = precision_recall_fscore_support(y, pred, labels=labels, zero_division=0)
    for c, a, b, d, s in zip(labels, P, R, F, S):
        per_class.append({"model": name, "class": c, "precision": a, "recall": b, "f1": d, "support": s})
    pd.DataFrame(confusion_matrix(y, pred, labels=labels), index=labels, columns=labels).to_csv(
        OUT / f"confusion_{name.split()[0].lower()}.csv")
    per_site[name] = pd.Series(pred == y).groupby(groups).mean()

comparison = pd.DataFrame(rows).set_index("model").round(3)
comparison.to_csv(OUT / "table_model_comparison.csv")
pd.DataFrame(per_class).round(3).to_csv(OUT / "table_per_class.csv", index=False)
site_table = pd.DataFrame(per_site).round(2)
site_table.insert(0, "clips", pd.Series(groups).value_counts())
site_table.to_csv(OUT / "table_per_site.csv")
print(comparison, "\n")

# ---------- per-site accuracy spread (each site = one fold) ----------
spread = pd.DataFrame({m: [site_table[m].mean(), site_table[m].std(), site_table[m].median()]
                       for m in per_site}, index=["mean_site_acc", "sd_site_acc", "median_site_acc"]).round(3)
spread.to_csv(OUT / "table_site_spread.csv")
print(spread, "\n")

# ---------- reference: random clip-level split (inflated, not used for SO7) ----------
ref = []
for name in ("Random Forest", "SVM"):
    cols, make = MODELS[name]
    Xtr, Xte, ytr, yte = train_test_split(df[cols], y, test_size=0.2, random_state=42, stratify=y)
    pred = make().fit(Xtr, ytr).predict(Xte)
    ref.append({"model": name, "random_split_accuracy": accuracy_score(yte, pred),
                "random_split_macro_f1": f1_score(yte, pred, average="macro"),
                "loso_accuracy": comparison.loc[name, "accuracy"]})
pd.DataFrame(ref).round(3).to_csv(OUT / "table_random_vs_loso.csv", index=False)
print(pd.DataFrame(ref).round(3))
print(f"\nSaved to {OUT}")
