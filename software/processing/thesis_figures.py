"""
Chapter 6 figures (PNG, 200 dpi) from the outputs of thesis_results.py.

    python thesis_figures.py      # -> data/results/fig_*.png
"""

from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.metrics import confusion_matrix, roc_curve, auc

BASE_DIR = Path(__file__).resolve().parents[2]
RES = BASE_DIR / "data" / "results"

INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"
BLUE = "#2a78d6"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]   # categorical order, never cycled
TARGET = "#e34948"

plt.rcParams.update({
    "font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2,
    "ytick.color": INK2, "axes.titlecolor": INK, "axes.titlesize": 11, "axes.spines.top": False,
    "axes.spines.right": False, "savefig.dpi": 200, "savefig.bbox": "tight", "figure.facecolor": "white",
})

data = np.load(RES / "loso_probas.npz", allow_pickle=True)
labels = list(data["labels"])
y = data["y"]
groups = data["groups"]
MODELS = {"Random Forest": "Random_Forest", "SVM": "SVM",
          "YAMNet CNN + LR": "YAMNet_CNN_+_LR", "Ensemble (SVM + YAMNet)": "Ensemble_(SVM_+_YAMNet)"}
probas = {name: data[key] for name, key in MODELS.items()}
preds = {name: np.array(labels)[p.argmax(1)] for name, p in probas.items()}
nice = [l.capitalize() for l in labels]

# ---------- Figure: confusion matrices (row-normalised %, counts below) ----------
fig, axes = plt.subplots(2, 2, figsize=(10, 9))
for ax, (name, pred) in zip(axes.flat, preds.items()):
    cm = confusion_matrix(y, pred, labels=labels)
    pct = 100 * cm / cm.sum(1, keepdims=True)
    ax.imshow(pct, cmap="Blues", vmin=0, vmax=100)
    for i in range(len(labels)):
        for j in range(len(labels)):
            ax.text(j, i, f"{pct[i, j]:.0f}%\n({cm[i, j]})", ha="center", va="center", fontsize=8,
                    color="white" if pct[i, j] > 55 else INK)
    ax.set_xticks(range(len(labels)), nice, rotation=30, ha="right")
    ax.set_yticks(range(len(labels)), nice)
    ax.set_xlabel("Predicted class")
    ax.set_ylabel("True class")
    ax.set_title(f"{name}\naccuracy {np.mean(pred == y):.1%}")
    ax.spines[:].set_visible(False)
fig.tight_layout()
fig.savefig(RES / "fig_confusion_matrices.png")
plt.close(fig)

# Best model alone, larger, for the main text
name = "Ensemble (SVM + YAMNet)"
cm = confusion_matrix(y, preds[name], labels=labels)
pct = 100 * cm / cm.sum(1, keepdims=True)
fig, ax = plt.subplots(figsize=(6, 5))
ax.imshow(pct, cmap="Blues", vmin=0, vmax=100)
for i in range(len(labels)):
    for j in range(len(labels)):
        ax.text(j, i, f"{pct[i, j]:.0f}%\n({cm[i, j]})", ha="center", va="center", fontsize=9,
                color="white" if pct[i, j] > 55 else INK)
ax.set_xticks(range(len(labels)), nice, rotation=30, ha="right")
ax.set_yticks(range(len(labels)), nice)
ax.set_xlabel("Predicted class")
ax.set_ylabel("True class")
ax.spines[:].set_visible(False)
fig.savefig(RES / "fig_confusion_ensemble.png")
plt.close(fig)

# ---------- Figure: model accuracy against the 85% target ----------
comp = pd.read_csv(RES / "table_model_comparison.csv", index_col=0)
fig, ax = plt.subplots(figsize=(7, 3.2))
order = comp["accuracy"].sort_values().index
bars = ax.barh(range(len(order)), 100 * comp.loc[order, "accuracy"], color=BLUE, height=0.55)
ax.set_yticks(range(len(order)), order)
ax.axvline(85, color=TARGET, lw=1.5, ls="--")
ax.text(85.3, len(order) - 0.45, "85% target (SO7)", color=INK2, fontsize=9, va="bottom")
for b, v in zip(bars, comp.loc[order, "accuracy"]):
    ax.text(b.get_width() + 0.4, b.get_y() + b.get_height() / 2, f"{v:.1%}", va="center", color=INK, fontsize=9)
ax.set_xlim(50, 100)
ax.set_xlabel("Leave-one-site-out accuracy (%)")
ax.grid(axis="x", color=GRID, lw=0.8)
ax.set_axisbelow(True)
fig.savefig(RES / "fig_model_accuracy.png")
plt.close(fig)

# ---------- Figure: one-vs-rest ROC curves of the ensemble ----------
p = probas[name]
fig, ax = plt.subplots(figsize=(5.5, 5))
for k, (c, color) in enumerate(zip(labels, SERIES)):
    fpr, tpr, _ = roc_curve(y == c, p[:, k])
    ax.plot(fpr, tpr, color=color, lw=2, label=f"{c.capitalize()} (AUC {auc(fpr, tpr):.3f})")
ax.plot([0, 1], [0, 1], color=GRID, lw=1, ls="--")
ax.set_xlabel("False positive rate")
ax.set_ylabel("True positive rate")
ax.legend(frameon=False, loc="lower right")
ax.grid(color=GRID, lw=0.6)
fig.savefig(RES / "fig_roc_ensemble.png")
plt.close(fig)

# ---------- Figure: accuracy of each site when it was held out ----------
site_acc = pd.Series(preds[name] == y).groupby(groups).mean().sort_values()
counts = pd.Series(groups).value_counts()
fig, ax = plt.subplots(figsize=(7, 8))
ax.barh(range(len(site_acc)), 100 * site_acc.values, color=BLUE, height=0.65)
for i, v in enumerate(site_acc.values):
    ax.text(100 * v + 1, i, f"{v:.0%}", va="center", fontsize=7, color=INK)
ax.set_yticks(range(len(site_acc)), [f"{s}  (n={counts[s]})" for s in site_acc.index], fontsize=8)
ax.axvline(85, color=TARGET, lw=1.5, ls="--")
ax.set_xlabel("Accuracy on the held-out site (%)")
ax.set_xlim(0, 108)
ax.grid(axis="x", color=GRID, lw=0.8)
ax.set_axisbelow(True)
fig.savefig(RES / "fig_site_accuracy.png")
plt.close(fig)

# ---------- Figure: clips per class ----------
summ = pd.read_csv(RES / "table_dataset_summary.csv", index_col=0).drop(index="Total")
summ = summ.sort_values("clips")
fig, ax = plt.subplots(figsize=(6, 2.8))
bars = ax.barh([s.capitalize() for s in summ.index], summ["clips"], color=BLUE, height=0.55)
for b, (_, r) in zip(bars, summ.iterrows()):
    ax.text(b.get_width() + 8, b.get_y() + b.get_height() / 2,
            f"{int(r.clips)} clips, {int(r.sites)} sites", va="center", fontsize=9, color=INK)
ax.set_xlim(0, summ["clips"].max() * 1.35)
ax.set_xlabel("Number of 5-second clips")
ax.grid(axis="x", color=GRID, lw=0.8)
ax.set_axisbelow(True)
fig.savefig(RES / "fig_dataset_classes.png")
plt.close(fig)

print("Figures saved to", RES)
