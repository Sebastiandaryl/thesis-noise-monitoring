from pathlib import Path
import numpy as np
import pandas as pd
import joblib
import subprocess
import warnings
import soundfile as sf

from extract_features import extract_features   # same features as training
from extract_yamnet import yamnet_features

warnings.filterwarnings("ignore")

# =========================
# PATH SETUP

# =========================

BASE_DIR = Path(__file__).resolve().parents[2]

# Saved by train_rf.py: ensemble_model.joblib (SVM + YAMNet), or a single
# model such as svm_model.joblib / rf_model.joblib / yamnet_model.joblib
MODEL_DIR = BASE_DIR / "data" / "features"
MODEL_PATH = MODEL_DIR / "ensemble_model.joblib"

TEMP_WAV = BASE_DIR / "data" / "temp_record.wav"

RECORD_SECONDS = 5   # must match the 5-second training clips
# The INMP441 gives a loud low-frequency thump for ~0.7 s each time arecord
# starts after being idle; field_record.py records clips back to back, so the
# training clips almost never have it. Record this much extra and drop it.
WARMUP_SECONDS = 1

# =========================
# LOAD MODEL
# =========================

print("Loading model...")

loaded = joblib.load(MODEL_PATH)
if isinstance(loaded, dict):   # ensemble: average the members' probabilities
    members = [joblib.load(MODEL_DIR / f"{m}_model.joblib") for m in loaded["members"]]
    class_names = np.array(loaded["classes"])
else:
    members = [loaded]
    class_names = loaded.classes_

print("Model loaded.")

# =========================
# RECORD AUDIO USING ARECORD
# =========================

def record_audio():

    print(f"\nRecording {RECORD_SECONDS} seconds...")

    command = [
        "arecord",
        "-D", "plughw:CARD=sndrpigooglevoi,DEV=0",
        "-f", "S32_LE",
        "-r", "44100",
        "-c", "1",
        "-d", str(WARMUP_SECONDS + RECORD_SECONDS),
        str(TEMP_WAV)
    ]

    subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Keep only the last RECORD_SECONDS (drop the start-up thump)
    audio, sr = sf.read(TEMP_WAV, dtype="int32")
    sf.write(TEMP_WAV, audio[WARMUP_SECONDS * sr:], sr, subtype="PCM_32")

    print("Recording complete.")

# =========================
# MAIN LOOP
# =========================

while True:

    input("\nPress ENTER to record...")

    record_audio()

    features = extract_features(TEMP_WAV)
    features.update(yamnet_features(TEMP_WAV))
    row = pd.DataFrame([features])

    # Each member picks its own columns, in the order it was trained with
    probabilities = np.mean([m.predict_proba(row[m.feature_names_in_])[0] for m in members], axis=0)
    prediction = class_names[np.argmax(probabilities)]

    print("\nPredicted class:", prediction)
    print("Confidence:", np.max(probabilities))

    # ++++ OPTIONAL DISPLAY FEATURE ++++
    # Top 3 class probabilities (can remove if not needed)

    top3_idx = np.argsort(probabilities)[-3:][::-1]

    print("\nTop 3 probabilities:")
    for i in top3_idx:
        print(f"{class_names[i]} : {probabilities[i]:.3f}")
