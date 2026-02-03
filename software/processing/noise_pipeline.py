import numpy as np
import scipy.io.wavfile as wav
from scipy.signal import bilinear, lfilter
import math
import os

# =====================================
# A-WEIGHTING FILTER (IEC/CD 1672)
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
# LOAD AUDIO FILE (ROBUST PATH)
# =====================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
wav_path = os.path.join(
    BASE_DIR,
    "..",
    "..",
    "data",
    "raw_samples",
    "loud_noise.wav"
)

if not os.path.exists(wav_path):
    raise FileNotFoundError(f"Audio file not found: {wav_path}")

fs, data = wav.read(wav_path)

# =====================================
# PREPROCESS AUDIO
# =====================================
data = data.astype(np.float64)

# Use mono if stereo
if data.ndim > 1:
    data = data[:, 0]

# Normalize by dtype
if data.dtype == np.int16:
    data = data / 32768.0
elif data.dtype == np.int32:
    data = data / (2**31)

# =====================================
# APPLY A-WEIGHTING
# =====================================
b, a = a_weighting(fs)
weighted = lfilter(b, a, data)

# =====================================
# RMS & RELATIVE dB
# =====================================
rms = np.sqrt(np.mean(weighted ** 2))

RMS_REF = 0.005  # quiet-room reference (relative, not absolute SPL)
db = 20 * math.log10(rms / RMS_REF)
db = max(db, 0)  # clamp for display

# =====================================
# CLASSIFICATION (RELATIVE)
# =====================================
if db < 20:
    level = "LOW noise (quiet)"
elif db < 50:
    level = "MODERATE noise"
else:
    level = "HIGH noise"

# =====================================
# OUTPUT
# =====================================
print("----- Noise Analysis Result -----")
print(f"Sample rate        : {fs} Hz")
print(f"A-weighted RMS     : {rms:.6f}")
print(f"Relative SPL       : {db:.2f} dB")
print(f"Noise classification: {level}")
