"""
Figure 3.1 (conceptual flow) and Figure 4.1 (system architecture) as PNG,
drawn to match the final system described in the thesis.

    python thesis_diagrams.py     # -> data/results/fig3_1_conceptual_flow.png, fig4_1_system_architecture.png
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

BASE_DIR = Path(__file__).resolve().parents[2]
RES = BASE_DIR / "data" / "results"

INK, INK2, LINE = "#0b0b0b", "#52514e", "#8a8984"
# light fill + strong edge per stage, from the palette in thesis_figures.py
BLUE = ("#e8f1fb", "#2a78d6")
ORANGE = ("#fdeee6", "#eb6834")
GREEN = ("#e5f6ef", "#1baf7a")
YELLOW = ("#fdf4dc", "#c98a00")
PINK = ("#fbebf2", "#d1608e")
GREY = ("#f3f2ef", "#8a8984")

plt.rcParams.update({"font.size": 9, "figure.facecolor": "white", "savefig.dpi": 300, "savefig.bbox": "tight"})


def box(ax, x, y, w, h, title, lines, color, title_size=10.5, line_size=8.6, dashed=False):
    """Rounded box with a bold title and body lines; (x, y) is the top-left corner."""
    fill, edge = color
    ax.add_patch(FancyBboxPatch((x, y - h), w, h, boxstyle="round,pad=0,rounding_size=0.012",
                                fc=fill, ec=edge, lw=1.4, ls="--" if dashed else "-"))
    ax.text(x + w / 2, y - 0.022, title, ha="center", va="top", fontsize=title_size, weight="bold", color=INK)
    ax.text(x + w / 2, y - 0.058, "\n".join(lines), ha="center", va="top", fontsize=line_size,
            color=INK2, linespacing=1.45)


def arrow(ax, x1, y1, x2, y2, text=None, dashed=False):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="-|>", color=LINE, lw=1.4, ls="--" if dashed else "-",
                                shrinkA=0, shrinkB=0, mutation_scale=12))
    if text:
        ax.text((x1 + x2) / 2 + 0.01, (y1 + y2) / 2, text, ha="left", va="center", fontsize=7.8,
                color=INK2, style="italic")


def conceptual_flow():
    fig = plt.figure(figsize=(7.2, 10.2))
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    X, W = 0.04, 0.6
    stages = [
        ("1. Acoustic Data Acquisition", ["Raspberry Pi 4 + INMP441 MEMS microphone (I²S) + NEO-6M GPS",
                                          "in a 3D-printed case  ·  44.1 kHz, 32-bit, mono",
                                          "28 field sites in Metro Manila  ·  1,632 five-second clips"], BLUE, 0.118),
        ("2. Preprocessing", ["Segmentation into 5-s clips  ·  mono  ·  peak normalization",
                              "First second dropped in live use (microphone start-up)",
                              "A-weighted sound level L_Aeq of each clip"], BLUE, 0.118),
        ("3. Feature Extraction", ["199 handcrafted features: MFCC with deltas, mel bands,",
                                   "spectral, chroma, contrast, onset, and RMS statistics",
                                   "YAMNet embedding (pretrained CNN): 1,024 + 521 values"], ORANGE, 0.118),
        ("4. Noise Source Classification", ["Ensemble of SVM + YAMNet (used live); RF, SVM, YAMNet compared",
                                            "Quiet-level rule: L_Aeq below 40 dB(A) → ambient",
                                            "5 categories: vehicular, industrial, human, commercial, ambient",
                                            "Leave-one-site-out testing: 87.9% accuracy (SO2, SO7)"], GREEN, 0.14),
        ("5. Forecasting and Risk Assessment", ["15-minute forecast: energy average of the last 15 readings",
                                                "WHO guideline values (55 dB day, 40 dB night)",
                                                "Alerts at 70 dB and 85 dB  ·  high-risk zones (SO5, SO6)"], YELLOW, 0.118),
        ("6. GIS Dashboard and Alerts", ["Public map: level, noise source, forecast, livability grade",
                                         "Staff dashboard: alerts, trends, reports for planners",
                                         "Supports urban planning and public health (SO4)"], PINK, 0.118),
    ]
    y, gap, tops = 0.975, 0.042, []
    for title, lines, color, h in stages:
        box(ax, X, y, W, h, title, lines, color)
        tops.append((y, h))
        y -= h + gap
    for (y1, h1), (y2, _) in zip(tops, tops[1:]):
        arrow(ax, X + W / 2, y1 - h1, X + W / 2, y2)
    # chaos branch beside feature extraction and classification
    cx, cw = 0.68, 0.29
    y3, h3 = tops[2]
    box(ax, cx, y3, cw, h3, "Chaos-Based Analysis", ["Phase space (τ = 15, m = 3)",
                                                    "Largest Lyapunov exponent λ",
                                                    "Correlation dim. D₂, fractal dim. D_f"], ORANGE, title_size=9.5, line_size=8)
    arrow(ax, X + W, y3 - h3 / 2, cx, y3 - h3 / 2)
    y4, h4 = tops[3]
    box(ax, cx, y4, cw, h4, "Chaos Evaluation", ["Differences between categories",
                                                "(Kruskal–Wallis, SO3)",
                                                "With vs. without chaos features",
                                                "(Wilcoxon, SO1); not used live"], GREY, title_size=9.5, line_size=8, dashed=True)
    arrow(ax, cx + cw / 2, y3 - h3, cx + cw / 2, y4)
    fig.savefig(RES / "fig3_1_conceptual_flow.png")
    plt.close(fig)


def system_architecture():
    fig = plt.figure(figsize=(7.4, 10.6))
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    # column headings
    LX, LW, RX, RW = 0.17, 0.45, 0.69, 0.29
    ax.text(LX + LW / 2, 0.985, "Live operation on the Raspberry Pi", ha="center", fontsize=10, weight="bold", color=INK)
    ax.text(RX + RW / 2, 0.985, "Offline, on a computer", ha="center", fontsize=10, weight="bold", color=INK)
    layers = [("Data\nacquisition", BLUE, 0.96, 0.17), ("Signal processing\nand feature\nengineering", ORANGE, 0.77, 0.19),
              ("Machine learning\nand nonlinear\nanalysis", GREEN, 0.56, 0.2), ("Visualization\nand decision\nsupport", PINK, 0.34, 0.33)]
    for name, (fill, edge), top, h in layers:
        ax.add_patch(FancyBboxPatch((0.01, top - h), 0.98, h, boxstyle="round,pad=0,rounding_size=0.01",
                                    fc=fill, ec="none", alpha=0.55))
        ax.text(0.085, top - h / 2, name, ha="center", va="center", fontsize=9, weight="bold", color=edge, linespacing=1.3)
    # layer 1
    box(ax, LX, 0.945, LW, 0.14, "Acquisition unit (3D-printed case)",
        ["INMP441 MEMS microphone over I²S", "Raspberry Pi 4 Model B (4 GB)  ·  power bank",
         "NEO-6M GPS module (position of each reading)"], BLUE)
    box(ax, RX, 0.945, RW, 0.14, "Field dataset",
        ["28 sites, Metro Manila", "1,632 labeled 5-s clips", "microphone outside the case"], BLUE)
    # layer 2
    box(ax, LX, 0.755, LW, 0.16, "Per clip, about 1 s of processing",
        ["Record 6 s, drop the first second → 5-s clip", "Peak normalization  ·  A-weighted L_Aeq",
         "199 handcrafted features + YAMNet embedding"], ORANGE)
    box(ax, RX, 0.755, RW, 0.16, "Feature sets",
        ["Same 199 features + YAMNet", "Chaos metrics λ, D₂, D_f",
         "(about 3 s per clip, so", "not computed live)"], ORANGE)
    # layer 3
    box(ax, LX, 0.545, LW, 0.17, "Classification",
        ["Quiet-level rule: below 40 dB(A) → ambient", "Ensemble: SVM + YAMNet logistic regression",
         "→ noise category + probability of each class", "15-minute forecast (energy average, logger)"], GREEN)
    box(ax, RX, 0.545, RW, 0.17, "Training and evaluation",
        ["RF, SVM, YAMNet + LR, ensemble", "Leave-one-site-out (28 folds)", "With vs. without chaos",
         "(Wilcoxon); Kruskal–Wallis"], GREEN)
    # layer 4
    box(ax, LX, 0.325, LW, 0.1, "Reading sent as JSON over HTTPS",
        ["site ID, time, L_Aeq, forecast, category,", "probabilities, GPS fix and position"], PINK, line_size=8.3)
    box(ax, LX, 0.205, LW, 0.085, "Dashboard server (PythonAnywhere)",
        ["stores readings  ·  WHO check  ·  70 / 85 dB alerts"], PINK, line_size=8.3)
    box(ax, 0.17, 0.095, 0.38, 0.08, "Public view", ["map, source, forecast, livability grade"], PINK, line_size=8.2)
    box(ax, 0.6, 0.095, 0.38, 0.08, "Staff view", ["alerts, trends, class probabilities, reports"], PINK, line_size=8.2)
    # arrows, live column
    cx = LX + LW / 2
    arrow(ax, cx, 0.805, cx, 0.755); arrow(ax, cx, 0.595, cx, 0.545); arrow(ax, cx, 0.375, cx, 0.325)
    arrow(ax, cx, 0.225, cx, 0.205)
    ax.plot([cx, cx], [0.12, 0.108], color=LINE, lw=1.4); ax.plot([0.36, 0.79], [0.108, 0.108], color=LINE, lw=1.4)
    arrow(ax, 0.36, 0.108, 0.36, 0.095); arrow(ax, 0.79, 0.108, 0.79, 0.095)
    # arrows, offline column
    rx = RX + RW / 2
    arrow(ax, rx, 0.805, rx, 0.755); arrow(ax, rx, 0.595, rx, 0.545)
    arrow(ax, RX, 0.46, LX + LW, 0.46, dashed=True)
    ax.text((RX + LX + LW) / 2, 0.47, "trained\nmodels", ha="center", va="bottom", fontsize=7.2, color=INK2,
            style="italic", linespacing=1.1)
    fig.savefig(RES / "fig4_1_system_architecture.png")
    plt.close(fig)


if __name__ == "__main__":
    conceptual_flow()
    system_architecture()
    print("saved", RES / "fig3_1_conceptual_flow.png", "and", RES / "fig4_1_system_architecture.png")
