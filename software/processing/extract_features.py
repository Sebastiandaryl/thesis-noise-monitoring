import csv
import numpy as np
import librosa
from pathlib import Path

# -----------------------------
# Paths
# -----------------------------
DATASET_DIR = Path.home() / "thesis" / "data" / "dataset_48k_balanced"
OUT_DIR = Path.home() / "thesis" / "data" / "features"
OUT_CSV = OUT_DIR / "features.csv"

# -----------------------------
# Feature settings (keep stable)
# -----------------------------
TARGET_SR = 48000
N_MFCC = 13
N_FFT = 2048
HOP_LENGTH = 512

CLASSES = {
    "ambient": DATASET_DIR / "ambient",
    "vehicle": DATASET_DIR / "vehicle",
    "voices":  DATASET_DIR / "voices"
}

def extract_one(filepath: Path):
    # Load as mono, resample if needed
    y, sr = librosa.load(filepath, sr=TARGET_SR, mono=True)

    # RMS energy (mean + std)
    rms = librosa.feature.rms(y=y, frame_length=N_FFT, hop_length=HOP_LENGTH)[0]
    rms_mean = float(np.mean(rms))
    rms_std = float(np.std(rms))

    # MFCCs (mean + std for each coefficient)
    mfcc = librosa.feature.mfcc(y=y, sr=TARGET_SR, n_mfcc=N_MFCC,
                                n_fft=N_FFT, hop_length=HOP_LENGTH)
    mfcc_mean = np.mean(mfcc, axis=1)
    mfcc_std = np.std(mfcc, axis=1)

    # Spectral features (mean + std)
    centroid = librosa.feature.spectral_centroid(y=y, sr=TARGET_SR,
                                                 n_fft=N_FFT, hop_length=HOP_LENGTH)[0]
    bandwidth = librosa.feature.spectral_bandwidth(y=y, sr=TARGET_SR,
                                                   n_fft=N_FFT, hop_length=HOP_LENGTH)[0]
    rolloff = librosa.feature.spectral_rolloff(y=y, sr=TARGET_SR,
                                               n_fft=N_FFT, hop_length=HOP_LENGTH, roll_percent=0.85)[0]
    flatness = librosa.feature.spectral_flatness(y=y, n_fft=N_FFT, hop_length=HOP_LENGTH)[0]

    spec = [
        float(np.mean(centroid)), float(np.std(centroid)),
        float(np.mean(bandwidth)), float(np.std(bandwidth)),
        float(np.mean(rolloff)), float(np.std(rolloff)),
        float(np.mean(flatness)), float(np.std(flatness))
    ]

    # Combine into one feature vector
    feats = [rms_mean, rms_std]
    feats += mfcc_mean.tolist() + mfcc_std.tolist()
    feats += spec

    return feats

def build_header():
    header = ["filepath", "label", "rms_mean", "rms_std"]
    for i in range(N_MFCC):
        header.append(f"mfcc{i+1}_mean")
    for i in range(N_MFCC):
        header.append(f"mfcc{i+1}_std")
    header += [
        "spec_centroid_mean", "spec_centroid_std",
        "spec_bandwidth_mean", "spec_bandwidth_std",
        "spec_rolloff_mean", "spec_rolloff_std",
        "spec_flatness_mean", "spec_flatness_std"
    ]
    return header

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    rows = []
    total = 0

    for label, folder in CLASSES.items():
        wavs = sorted(folder.glob("*.wav"))
        for fp in wavs:
            try:
                feats = extract_one(fp)
                rows.append([str(fp), label] + feats)
                total += 1
                if total % 50 == 0:
                    print(f"Processed {total} files...")
            except Exception as e:
                print(f"[SKIP] {fp.name}: {e}")

    # Write CSV
    header = build_header()
    with open(OUT_CSV, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)

    print(f"\n Done. Wrote {len(rows)} rows to: {OUT_CSV}")

if __name__ == "__main__":
    main()
