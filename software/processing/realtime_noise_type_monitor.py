import numpy as np
import scipy.io.wavfile as wav
from scipy.signal import bilinear, lfilter
import math
import os
import time
import subprocess

# =====================================
# A-WEIGHTING FILTER
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
# SYSTEM SETTINGS (CALIBRATED)
# =====================================
SAMPLE_RATE = 48000
DURATION = 1                 # seconds per chunk
RMS_REF = 0.0004            # empirically measured quiet-room RMS
SOFTWARE_GAIN = 5.0        # compensates for low-sensitivity MEMS mic

# path so SSH / services work
TEMP_WAV = "/tmp/temp_chunk.wav"

# ALSA device
ARECORD_DEVICE = "plughw:CARD=sndrpigooglevoi,DEV=0"

print("\n🔴 REAL-TIME NOISE MONITORING (Ctrl+C to stop)\n")

try:
    while True:
        # ---------------------------------
        # RECORD AUDIO CHUNK
        # ---------------------------------
        rec = subprocess.run([
            "arecord",
            "-D", ARECORD_DEVICE,
            "-f", "S32_LE",
            "-r", str(SAMPLE_RATE),
            "-c", "1", # mono
            "-d", str(DURATION),
            TEMP_WAV
        ], capture_output=True, text=True)

        # ---------------------------------
        # FIX: Don’t crash if file missing
        # ---------------------------------
        if rec.returncode != 0 or not os.path.exists(TEMP_WAV):
            print("Warning: audio chunk not recorded. Retrying...")
            if rec.stderr:
                print("arecord error:", rec.stderr.strip())
            time.sleep(0.2)
            continue

        # ---------------------------------
        # LOAD AUDIO
        # ---------------------------------
        fs, data = wav.read(TEMP_WAV)
        data = data.astype(np.float64)

        # mono channel
        if data.ndim > 1:
            data = data[:, 0]

        # normalize 32-bit PCM
        data = data / (2**31)

        # ---------------------------------
        # A-WEIGHTING
        # ---------------------------------
        b, a = a_weighting(fs)
        weighted = lfilter(b, a, data)

        # apply software gain
        weighted = weighted * SOFTWARE_GAIN

        # ---------------------------------
        # RMS & RELATIVE dB
        # ---------------------------------
        rms = np.sqrt(np.mean(weighted ** 2))
        if rms <= 0:
            db = 0.0
        else:
            db = 20 * math.log10(rms / RMS_REF)

        db = max(db, 0)  # clamp negative values

        # ---------------------------------
        # FFT FOR NOISE TYPE IDENTIFICATION
        # (USE RAW SIGNAL - NOT A-WEIGHTED)
        # ---------------------------------
        fft = np.abs(np.fft.rfft(data))
        freqs = np.fft.rfftfreq(len(data), 1 / fs)

        # frequency bands
        low_band = (freqs >= 20) & (freqs <= 300)
        mid_band = (freqs >= 300) & (freqs <= 3400)

        low_energy = np.sum(fft[low_band])
        mid_energy = np.sum(fft[mid_band])

        if mid_energy > low_energy:
            noise_type = "HUMAN"
        else:
            noise_type = "CAR"

        # ---------------------------------
        # NOISE LEVEL (RELATIVE)
        # ---------------------------------
        if db < 20:
            level = "LOW"
        elif db < 35:
            level = "MODERATE"
        else:
            level = "HIGH"

        # ---------------------------------
        # LIVE OUTPUT
        # ---------------------------------
        print(f"SPL: {db:6.2f} dB | Level: {level:8} | Type: {noise_type}")

        time.sleep(0.2)

except KeyboardInterrupt:
    print("\n🟢 Monitoring stopped.")
    if os.path.exists(TEMP_WAV):
        os.remove(TEMP_WAV)
