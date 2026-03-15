from pathlib import Path
import warnings

import librosa
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# =========================
# PATH SETUP
# =========================
BASE_DIR = Path(__file__).resolve().parents[2]   # ~/thesis
DATASET_DIR = BASE_DIR / "data" / "dataset"
OUTPUT_DIR = BASE_DIR / "data" / "features"
OUTPUT_CSV = OUTPUT_DIR / "features.csv"

# =========================
# AUDIO SETTINGS
# =========================
TARGET_SR = 44100
N_MFCC = 13

# =========================
# CLASSES
# =========================
CLASSES = ["ambient", "commercial", "human", "industrial", "vehicular"]

# Allowed file extensions
AUDIO_EXTENSIONS = {".wav"}


def get_audio_files(folder: Path):
    return sorted(folder.rglob("*.wav"))

def extract_features(file_path: Path):
    """
    Extract fixed-length numerical features from one audio file.
    Returns a dictionary of features.
    """
    y, sr = librosa.load(file_path, sr=TARGET_SR, mono=True)

    # Basic safety check
    if len(y) == 0:
        raise ValueError("Empty audio file")

    # Optional normalization
    peak = np.max(np.abs(y))
    if peak > 0:
        y = y / peak

    features = {}

    # RMS
    rms = librosa.feature.rms(y=y)[0]
    features["rms_mean"] = float(np.mean(rms))
    features["rms_std"] = float(np.std(rms))

    # Zero-Crossing Rate
    zcr = librosa.feature.zero_crossing_rate(y)[0]
    features["zcr_mean"] = float(np.mean(zcr))
    features["zcr_std"] = float(np.std(zcr))

    # Spectral centroid
    centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
    features["centroid_mean"] = float(np.mean(centroid))
    features["centroid_std"] = float(np.std(centroid))

    # Spectral bandwidth
    bandwidth = librosa.feature.spectral_bandwidth(y=y, sr=sr)[0]
    features["bandwidth_mean"] = float(np.mean(bandwidth))
    features["bandwidth_std"] = float(np.std(bandwidth))

    # Spectral rolloff
    rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr)[0]
    features["rolloff_mean"] = float(np.mean(rolloff))
    features["rolloff_std"] = float(np.std(rolloff))

    # Spectral contrast
    contrast = librosa.feature.spectral_contrast(y=y, sr=sr)
    for i in range(contrast.shape[0]):
        features[f"contrast_{i+1}_mean"] = float(np.mean(contrast[i]))
        features[f"contrast_{i+1}_std"] = float(np.std(contrast[i]))

    # Chroma
    chroma = librosa.feature.chroma_stft(y=y, sr=sr)
    for i in range(chroma.shape[0]):
        features[f"chroma_{i+1}_mean"] = float(np.mean(chroma[i]))
        features[f"chroma_{i+1}_std"] = float(np.std(chroma[i]))

    # MFCC
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=N_MFCC)
    for i in range(N_MFCC):
        features[f"mfcc_{i+1}_mean"] = float(np.mean(mfcc[i]))
        features[f"mfcc_{i+1}_std"] = float(np.std(mfcc[i]))

    return features


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    rows = []
    total_files = 0
    total_errors = 0

    print(f"\nDataset directory: {DATASET_DIR}")
    print(f"Output CSV: {OUTPUT_CSV}\n")

    for label in CLASSES:
        class_dir = DATASET_DIR / label

        if not class_dir.exists():
            print(f"[WARNING] Missing class folder: {class_dir}")
            continue

        audio_files = get_audio_files(class_dir)
        print(f"[INFO] {label}: {len(audio_files)} files found")

        for file_path in audio_files:
            total_files += 1
            try:
                feat = extract_features(file_path)
                feat["label"] = label
                feat["filename"] = file_path.name
                feat["filepath"] = str(file_path)
                rows.append(feat)
            except Exception as e:
                total_errors += 1
                print(f"[ERROR] Failed: {file_path.name} -> {e}")

    if not rows:
        print("\n[FAILED] No features extracted. Check dataset path and audio files.")
        return

    df = pd.DataFrame(rows)

    # Put label and file info at the front
    front_cols = ["label", "filename", "filepath"]
    other_cols = [c for c in df.columns if c not in front_cols]
    df = df[front_cols + other_cols]

    df.to_csv(OUTPUT_CSV, index=False)

    print("\n========== EXTRACTION COMPLETE ==========")
    print(f"Total files scanned : {total_files}")
    print(f"Successful extracts : {len(df)}")
    print(f"Errors             : {total_errors}")
    print(f"Feature CSV saved  : {OUTPUT_CSV}")
    print("========================================\n")

    print("Class counts:")
    print(df["label"].value_counts())


if __name__ == "__main__":
    main()
