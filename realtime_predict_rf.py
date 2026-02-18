import numpy as np
import scipy.io.wavfile as wav
from scipy.signal import bilinear, lfilter
import math
import os
import time
import subprocess
import librosa
import joblib

# =====================================
# TRAINED RF MODEL ONCE
# =====================================
MODEL_PATH = "/home/aidrivennoise/thesis/data/features/rf_model.joblib"
clf = joblib.load(MODEL_PATH)

# =====================================
# A-WEIGHTING FILTER (UNCHANGED)
# =====================================
def a_weighting(fs):
    f1 = 20.598997
    f2 = 107.65265
    f3 = 737.86223
    f4 = 12194.217
    A1000 = 1.9997

    nums = [(2 * math.pi * f4) ** 2 * (10 ** (A1000 / 20)), 0, 0, 0, 0]
    dens = np.convolve(
        [1, 4 * math.pi * f4, (2 * math.pi * f4) ** 2],
        [1, 4 * math.pi * f1, (2 * math.pi * f1) ** 2]
    )
    dens = np.convolve(
        np.convolve(dens, [1, 2 * math.pi * f3]),
        [1, 2 * math.pi * f2]
    )

    return bilinear(nums, dens, fs)

# =====================================
# ML FEATURE EXTRACTION
# =====================================
def extract_ml_features(filepath):
    y, sr = librosa.load(filepath, sr=48000, mono=True)

    rms = librosa.feature.rms(y=y)[0]
    rms_mean = np.mean(rms)
    rms_std = np.std(rms)

    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
    mfcc_mean = np.mean(mfcc, axis=1)
    mfcc_std = np.std(mfcc, axis=1)

    centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
    bandwidth = librosa.feature.spectral_bandwidth(y=y, sr=sr)[0]
    rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr)[0]
    flatness = librosa.feature.spectral_flatness(y=y)[0]

    features = [rms_mean, rms_std]
    features += mfcc_mean.tolist() + mfcc_std.tolist()
    features += [
        np.mean(centroid), np.std(centroid),
        np.mean(bandwidth), np.std(bandwidth),
        np.mean(rolloff), np.std(rolloff),
        np.mean(flatness), np.std(flatness)
    ]

    return np.array(features).reshape(1, -1)

# =====================================
# SYSTEM SETTINGS (UNCHANGED)
# =====================================
SAMPLE_RATE = 48000
DURATION = 1
RMS_REF = 0.0004
SOFTWARE_GAIN = 5.0

TEMP_WAV = "/tmp/temp_chunk.wav"
ARECORD_DEVICE = "plughw:CARD=sndrpigooglevoi,DEV=0"

print("\n🔴 LIVE ML-BASED NOISE CLASSIFICATION (Ctrl+C to stop)\n")

try:
    while True:
        # ---------------------------------
        # RECORD AUDIO (UNCHANGED)
        # ---------------------------------
        rec = subprocess.run([
            "arecord",
            "-D", ARECORD_DEVICE,
            "-f", "S32_LE",
            "-r", str(SAMPLE_RATE),
            "-c", "1",
            "-d", str(DURATION),
            TEMP_WAV
        ], capture_output=True)

        if rec.returncode != 0 or not os.path.exists(TEMP_WAV):
            print("⚠️ Audio capture failed")
            time.sleep(0.2)
            continue

        # ---------------------------------
        # LOAD + NORMALIZE
        # ---------------------------------
        fs, data = wav.read(TEMP_WAV)
        data = data.astype(np.float64) / (2**31)

        if data.ndim > 1:
            data = data[:, 0]

        # ---------------------------------
        # RMS + RELATIVE dB
        # ---------------------------------
        b, a = a_weighting(fs)
        weighted = lfilter(b, a, data) * SOFTWARE_GAIN
        rms = np.sqrt(np.mean(weighted ** 2))
        db = 20 * math.log10(rms / RMS_REF) if rms > 0 else 0
        db = max(db, 0)

        # ---------------------------------
        # RF PREDICTION (LIVE)
        # ---------------------------------
        X = extract_ml_features(TEMP_WAV)
        noise_type = clf.predict(X)[0]

        # ---------------------------------
        # OUTPUT (LIVE)
        # ---------------------------------
        print(f"SPL: {db:6.2f} dB | TYPE: {noise_type.upper()}")

        time.sleep(0.2)

except KeyboardInterrupt:
    print("\n🟢 Monitoring stopped.")
    if os.path.exists(TEMP_WAV):
        os.remove(TEMP_WAV)