import argparse
import time
from pathlib import Path
import librosa
import numpy as np
import pandas as pd
import joblib
import sounddevice as sd
import warnings

from publish_reading import DASHBOARD_URL, compute_laeq, read_gps, send_reading

warnings.filterwarnings("ignore")

# =========================
# PATH SETUP
# =========================

BASE_DIR = Path(__file__).resolve().parents[2]

MODEL_PATH = BASE_DIR / "data" / "features" / "rf_model.joblib"
FEATURE_CSV = BASE_DIR / "data" / "features" / "features.csv"

TARGET_SR = 44100
RECORD_SECONDS = 3
N_MFCC = 13

# =========================
# LOAD MODEL + FEATURE NAMES
# =========================

print("Loading model...")

model = joblib.load(MODEL_PATH)

feature_df = pd.read_csv(FEATURE_CSV)
feature_columns = feature_df.drop(columns=["label", "filename", "filepath"]).columns

print("Model loaded.")

# =========================
# AUDIO RECORD FUNCTION
# =========================

def record_audio():

    print(f"\nRecording {RECORD_SECONDS} seconds...")

    audio = sd.rec(
        int(RECORD_SECONDS * TARGET_SR),
        samplerate=TARGET_SR,
        channels=1,
        dtype="float32"
    )

    sd.wait()

    print("Recording complete.")

    return audio.flatten()

# =========================
# FEATURE EXTRACTION
# =========================

def extract_features(y):

    peak = np.max(np.abs(y))
    if peak > 0:
        y = y / peak

    features = []

    # RMS
    rms = librosa.feature.rms(y=y)[0]
    features += [np.mean(rms), np.std(rms)]

    # ZCR
    zcr = librosa.feature.zero_crossing_rate(y)[0]
    features += [np.mean(zcr), np.std(zcr)]

    # Spectral centroid
    centroid = librosa.feature.spectral_centroid(y=y, sr=TARGET_SR)[0]
    features += [np.mean(centroid), np.std(centroid)]

    # Bandwidth
    bandwidth = librosa.feature.spectral_bandwidth(y=y, sr=TARGET_SR)[0]
    features += [np.mean(bandwidth), np.std(bandwidth)]

    # Rolloff
    rolloff = librosa.feature.spectral_rolloff(y=y, sr=TARGET_SR)[0]
    features += [np.mean(rolloff), np.std(rolloff)]

    # Spectral contrast
    contrast = librosa.feature.spectral_contrast(y=y, sr=TARGET_SR)
    for i in range(contrast.shape[0]):
        features += [np.mean(contrast[i]), np.std(contrast[i])]

    # Chroma
    chroma = librosa.feature.chroma_stft(y=y, sr=TARGET_SR)
    for i in range(chroma.shape[0]):
        features += [np.mean(chroma[i]), np.std(chroma[i])]

    # MFCC
    mfcc = librosa.feature.mfcc(y=y, sr=TARGET_SR, n_mfcc=N_MFCC)
    for i in range(N_MFCC):
        features += [np.mean(mfcc[i]), np.std(mfcc[i])]

    return features

# =========================
# MAIN LOOP
# =========================

parser = argparse.ArgumentParser(description="Record, classify and (optionally) send readings to the GIS dashboard.")
parser.add_argument("--site", help="node ID shown on the dashboard, e.g. S01. Without it nothing is sent.")
parser.add_argument("--dashboard", default=DASHBOARD_URL, help="POST address of the dashboard (default: the PythonAnywhere site)")
parser.add_argument("--continuous", action="store_true", help="keep recording without pressing ENTER (for running on boot)")
parser.add_argument("--interval", type=float, default=0, help="extra seconds to wait between recordings in --continuous mode")
parser.add_argument("--gps", action="store_true", help="read the GPS module and send the node's position")
args = parser.parse_args()

while True:

    if args.continuous:
        if args.interval:
            time.sleep(args.interval)
    else:
        input("\nPress ENTER to record...")

    audio = record_audio()

    # Sound level from the raw audio, before extract_features normalizes it
    laeq = compute_laeq(audio, TARGET_SR)

    features = extract_features(audio)

    X = pd.DataFrame([features], columns=feature_columns)

    prediction = model.predict(X)[0]
    probabilities = model.predict_proba(X)[0]

    print("\nPredicted class:", prediction)
    print("Confidence:", np.max(probabilities))
    print(f"Level: {laeq:.1f} dB(A)")

    # ++++ optional ++++
 
    class_names = model.classes_

    top3_idx = np.argsort(probabilities)[-3:][::-1]

    print("\nTop 3 probabilities:")
    for i in top3_idx:
        print(f"{class_names[i]} : {probabilities[i]:.3f}")
    # ++++ optional ++++

    if args.site:
        ok = send_reading(
            site_id=args.site,
            laeq_db=laeq,
            category=prediction,
            probabilities=dict(zip(class_names, probabilities)),
            gps=read_gps() if args.gps else None,
            url=args.dashboard,
        )
        print("Sent to dashboard." if ok else "Not sent (dashboard unreachable).")
