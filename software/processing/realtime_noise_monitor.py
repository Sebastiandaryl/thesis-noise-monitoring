import numpy as np
import scipy.io.wavfile as wav
from scipy.signal import bilinear, lfilter
import math
import os
import time
import subprocess

# ===============================
# A-WEIGHTING FILTER
# ===============================
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

# ===============================
# SETTINGS
# ===============================
SAMPLE_RATE = 48000
DURATION = 1           # seconds per chunk
RMS_REF = 0.005        # quiet room reference
TEMP_WAV = "temp_chunk.wav"

print("🔴 Real-time Noise Monitoring Started (Ctrl+C to stop)\n")

try:
    while True:
        # -------------------------------
        # RECORD 1-SECOND AUDIO CHUNK
        # -------------------------------
        subprocess.run([
            "arecord",
            "-D", "hw:3,0",
            "-f", "S32_LE",
            "-r", str(SAMPLE_RATE),
            "-c", "2",
            "-d", str(DURATION),
            TEMP_WAV
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # -------------------------------
        # LOAD AUDIO
        # -------------------------------
        fs, data = wav.read(TEMP_WAV)
        data = data.astype(np.float64)

        if data.ndim > 1:
            data = data[:, 0]

        data = data / (2**31)

        # -------------------------------
        # APPLY A-WEIGHTING
        # -------------------------------
        b, a = a_weighting(fs)
        weighted = lfilter(b, a, data)

        # -------------------------------
        # RMS & dB
        # -------------------------------
        rms = np.sqrt(np.mean(weighted ** 2))
        db = 20 * math.log10(rms / RMS_REF)

        # -------------------------------
        # CLASSIFICATION
        # -------------------------------
        if db < 20:
            level = "LOW (Quiet)"
        elif db < 50:
            level = "MODERATE (Human activity)"
        else:
            level = "HIGH (Loud environment)"

        print(f"SPL: {db:6.2f} dB | {level}")

        time.sleep(0.2)

except KeyboardInterrupt:
    print("\n🟢 Monitoring stopped.")
    if os.path.exists(TEMP_WAV):
        os.remove(TEMP_WAV)
