from pathlib import Path
import re

import numpy as np
import pandas as pd
import joblib

from sklearn.model_selection import train_test_split, LeaveOneGroupOut, cross_val_predict
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score, balanced_accuracy_score

# =========================
# PATH SETUP
# =========================

BASE_DIR = Path(__file__).resolve().parents[2]

FEATURES_CSV = BASE_DIR / "data" / "features" / "features.csv"
YAMNET_CSV = BASE_DIR / "data" / "features" / "features_yamnet.csv"
MODEL_DIR = BASE_DIR / "data" / "features"

# Live prediction (realtime_predict_rf.py) loads the model saved for this name.
LIVE_MODEL = "ensemble"

# =========================
# LOAD FEATURES
# =========================

print("\nLoading features...")

df = pd.read_csv(FEATURES_CSV).drop(columns=["filepath"])
HAND_COLS = [c for c in df.columns if c not in ("label", "filename")]

# YAMNet embeddings (extract_yamnet.py); only clips present in both files are used
yam = pd.read_csv(YAMNET_CSV).drop(columns=["label"])
YAM_COLS = [c for c in yam.columns if c != "filename"]
df = df.merge(yam, on="filename")

print(f"Dataset size: {len(df)} samples")

# =========================
# PREPARE DATA
# =========================

X = df[HAND_COLS + YAM_COLS]
y = df["label"]

print(f"Feature count: {len(HAND_COLS)} handcrafted + {len(YAM_COLS)} YAMNet")

# =========================
# SITE (recording session) PER CLIP
# =========================
# Filenames look like <class>_real_<site>_clip_###.wav. Clips from the same
# session are near-duplicates, so they must never be split across train/test.

# Sessions recorded at the same place under different names count as one site.
SITE_ALIASES = {
    "commercial/baclaran_alley2": "commercial/baclaran_alley",
}

def site_of(filename, label):
    # Speaker-played sessions may reuse the same source videos, so all _sim_
    # clips of a class count as one site.
    if "_sim_" in filename:
        return f"{label}/sim"
    name = re.sub(r"_clip_\d+\.wav$", "", filename, flags=re.IGNORECASE)
    name = re.sub(rf"^{label}_(real_)?", "", name)
    site = f"{label}/{name}"
    return SITE_ALIASES.get(site, site)

groups = [site_of(f, l) for f, l in zip(df["filename"], df["label"])]

print("\nClips per site:")
print(pd.Series(groups).value_counts().sort_index().to_string())


# name -> (feature columns, model factory)
MODELS = {
    "rf": (HAND_COLS, lambda: RandomForestClassifier(
        n_estimators=200,
        max_depth=None,
        random_state=42,
        n_jobs=-1
    )),
    # SVM needs scaled features; C=10 was fixed before comparison (C=1..30 all within 1%)
    "svm": (HAND_COLS, lambda: make_pipeline(
        StandardScaler(),
        SVC(C=10, class_weight="balanced", probability=True, random_state=42)
    )),
    # Pretrained YAMNet CNN embeddings + logistic regression (transfer learning)
    "yamnet": (YAM_COLS, lambda: make_pipeline(
        StandardScaler(),
        LogisticRegression(C=0.1, max_iter=3000, class_weight="balanced")
    )),
}

# The ensemble averages the class probabilities of these models
ENSEMBLE = ("svm", "yamnet")

# =========================
# REFERENCE: RANDOM CLIP-LEVEL SPLIT (inflated, do not quote)
# =========================

X_train, X_test, y_train, y_test = train_test_split(
    df[HAND_COLS], y, test_size=0.2, random_state=42, stratify=y
)
random_acc = accuracy_score(y_test, MODELS["rf"][1]().fit(X_train, y_train).predict(X_test))
print(f"\n[reference only] Random clip-level split accuracy (RF): {random_acc:.3f}"
      " (inflated by near-duplicate clips from the same session)")

# =========================
# LEAVE-ONE-SITE-OUT EVALUATION (the honest number)
# =========================
# Each site is held out once; the model is trained on every other site and
# tested on the unseen one. Predictions are pooled into one report.

labels = sorted(y.unique())
is_real = ~df["filename"].str.contains("_sim_")
summary = {}
probas = {}


def report(name, y_pred):
    accuracy = accuracy_score(y, y_pred)
    balanced = balanced_accuracy_score(y, y_pred)
    summary[name] = (accuracy, balanced)

    print(f"\n{name.upper()} leave-one-site-out accuracy: {accuracy:.3f}  (balanced: {balanced:.3f})")

    # Speaker-played clips (<class>_sim_...) can be easier than real ones; the
    # real-world number is the accuracy on real field-recorded clips only.
    if (~is_real).any():
        real_acc = accuracy_score(y[is_real], y_pred[is_real])
        print(f"{name.upper()} accuracy on REAL field clips only ({is_real.sum()} clips): {real_acc:.3f}")

    print("\nClassification Report:")
    print(classification_report(y, y_pred))

    print("\nConfusion Matrix (rows = true, cols = predicted):")
    print(pd.DataFrame(confusion_matrix(y, y_pred, labels=labels), index=labels, columns=labels))

    per_site = (pd.DataFrame({"site": groups, "correct": y == y_pred, "pred": y_pred})
                .groupby("site")
                .agg(clips=("correct", "size"), accuracy=("correct", "mean"),
                     most_predicted=("pred", lambda p: p.value_counts().index[0])))
    print("\nPer-site accuracy when that site is unseen:")
    print(per_site.round(2).to_string())


for name, (cols, make_model) in MODELS.items():
    print(f"\n==================== {name.upper()} ====================")
    print("Running leave-one-site-out evaluation...")

    probas[name] = cross_val_predict(make_model(), df[cols], y, groups=groups,
                                     cv=LeaveOneGroupOut(), method="predict_proba")
    report(name, np.array(labels)[probas[name].argmax(axis=1)])

    # =========================
    # FINAL MODEL: TRAIN ON ALL SITES AND SAVE
    # =========================

    model = make_model().fit(df[cols], y)
    model_path = MODEL_DIR / f"{name}_model.joblib"
    joblib.dump(model, model_path)
    print(f"\nModel trained on all data and saved to: {model_path}")

print("\n==================== ENSEMBLE (" + " + ".join(ENSEMBLE).upper() + ") ====================")
report("ensemble", np.array(labels)[sum(probas[m] for m in ENSEMBLE).argmax(axis=1)])

ensemble_path = MODEL_DIR / "ensemble_model.joblib"
joblib.dump({"members": list(ENSEMBLE), "classes": labels}, ensemble_path)
print(f"\nEnsemble definition saved to: {ensemble_path} (uses the member model files)")

print("\n==================== SUMMARY (leave-one-site-out) ====================")
for name, (accuracy, balanced) in summary.items():
    print(f"{name.upper():9s} accuracy {accuracy:.3f}  balanced {balanced:.3f}"
          + ("   <- used by realtime_predict_rf.py" if name == LIVE_MODEL else ""))
