# AI-Driven Noise Pollution Monitoring

Undergraduate thesis project for the BS Computer Engineering program, Department of Electronics and Computer Engineering, Gokongwei College of Engineering, De La Salle University.

**Thesis title:** *AI-Driven Noise Pollution Monitoring and Chaos-Based Urban Acoustic Pattern Analysis Using Raspberry Pi*

**Researchers:** Giovan Marco B. Gingoyon, Andriel Dinn A. Ramos, James Daryl V. Sebastian

## Overview

The project uses Raspberry Pi sensor nodes with INMP441 MEMS microphones to record urban sound in Metro Manila and classify it into five noise categories:

| Class | Examples |
|---|---|
| `ambient` | background sound with no dominant source |
| `commercial` | shops, markets, business areas |
| `human` | voices, crowds, human activity |
| `industrial` | machinery, construction |
| `vehicular` | traffic, engines, horns |

This repository holds the current audio classification prototype: a feature extraction script, a Random Forest classifier, and a real-time script that records from the microphone and predicts the noise class.

## Repository structure

```
thesis-noise-monitoring/
├── data/
│   └── features/
│       ├── features.csv          # extracted features (1,873 clips, 74 features each)
│       └── rf_model.joblib       # trained Random Forest model
└── software/
    └── processing/
        ├── extract_features.py   # audio dataset -> features.csv
        ├── train_rf.py           # features.csv -> rf_model.joblib
        └── realtime_predict_rf.py  # live mic recording -> predicted class
```

The raw audio dataset (`data/dataset/`) is not stored in the repository because of its size. It is kept on the team's Google Drive.

## Pipeline

### 1. Feature extraction (`extract_features.py`)

Reads every `.wav` file under `data/dataset/<class>/`, resamples to 44.1 kHz mono, peak-normalizes it, and computes the mean and standard deviation of:

- RMS energy
- Zero-crossing rate
- Spectral centroid, bandwidth, and rolloff
- Spectral contrast (7 bands)
- Chroma (12 bins)
- MFCC (13 coefficients)

That gives 74 features per clip, written to `data/features/features.csv` along with the `label`, `filename`, and `filepath` columns.

Current dataset size:

| Class | Clips |
|---|---|
| ambient | 361 |
| commercial | 378 |
| human | 389 |
| industrial | 373 |
| vehicular | 372 |
| **Total** | **1,873** |

### 2. Training (`train_rf.py`)

Trains a `RandomForestClassifier` (200 trees) on an 80/20 stratified train/test split, prints the accuracy, classification report, and confusion matrix, and saves the model to `data/features/rf_model.joblib`.

### 3. Real-time prediction (`realtime_predict_rf.py`)

Each time you press Enter, it records 3 seconds from the default input device, extracts the same 74 features, and prints the predicted class, its confidence, and the top 3 class probabilities.

## Getting started

### Requirements

- Python 3.9+
- A Raspberry Pi with an INMP441 I2S microphone configured as the default audio input (for real-time prediction). Any computer with a microphone also works for testing.
- PortAudio (needed by `sounddevice`): `sudo apt install libportaudio2`

Install the Python packages:

```bash
pip install librosa numpy pandas scikit-learn joblib sounddevice
```

### Usage

Run the scripts from the repository root. Paths are resolved relative to the repository, so the working directory does not matter.

```bash
# 1. Extract features (needs the dataset in data/dataset/<class>/*.wav)
python software/processing/extract_features.py

# 2. Train the model
python software/processing/train_rf.py

# 3. Classify live audio
python software/processing/realtime_predict_rf.py
```

A trained model and feature file are already committed, so you can skip to step 3 without the dataset.

## Roadmap

These parts of the thesis are planned but not yet in this repository:

- Baseline CNN and chaos-enhanced CNN classifiers
- Chaos-based analysis using the Largest Lyapunov Exponent, correlation dimension (D2), and fractal dimension
- A-weighted decibel measurement checked against WHO limits (55 dB day, 40 dB night)
- Deployment across 9 sensor sites
- A GIS dashboard with a real-time, color-coded noise map, historical trends, and high-risk zone alerts
