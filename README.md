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

This repository holds the final single-node prototype: a Raspberry Pi 4 with an INMP441 microphone and a NEO-6M GPS module, the classification pipeline, the thesis results, and the GIS dashboard.

## Final results

- **Dataset:** 1,632 real field clips of 5 seconds each (ambient 557, human 353, industrial 314, commercial 255, vehicular 153)
- **Leave-one-site-out accuracy:** ensemble 87.9% (balanced 87.1%), SVM 86.2%, YAMNet 85.8%, Random Forest 80.1%
- **Live trials:** 222 readings, 85.1% correct (71.6% without the quiet-level rule)

The full report is `data/features/train_report_FINAL_2026-10-19.txt`.

## Repository structure

```
thesis-noise-monitoring/
├── requirements.txt
├── CLAUDE.md                 # detailed notes on how the scripts work together
├── models/yamnet.tflite      # pretrained YAMNet model
├── data/
│   ├── dataset/session_log.csv   # one row per field clip (GPS removed)
│   ├── features/             # feature CSVs, trained models, final training report
│   └── results/              # Chapter 6 tables and figures, live trial results
└── software/
    ├── processing/           # recording, features, training, live monitoring, thesis results
    └── dashboard/            # public noise map, staff dashboard and server
```

Not stored here: the audio clips, because of their size and because they can contain people's voices, and the home logger readings. The team keeps the audio on Google Drive.

## Pipeline

Run these from `software/processing/`.

```bash
python extract_features.py     # audio -> features.csv (199 handcrafted features)
python extract_yamnet.py       # audio -> features_yamnet.csv (YAMNet embeddings)
python extract_chaos.py        # audio -> features_chaos.csv (Lyapunov exponent, D2, Higuchi FD)
python train_rf.py             # feature CSVs -> rf, svm, yamnet and ensemble models
```

The three extraction steps need the audio in `data/dataset/<class>/`. The feature CSVs and trained models are already included, so `train_rf.py` runs without it.

On the Raspberry Pi:

```bash
python realtime_predict_rf.py  # press Enter, record 5 s, print the prediction
python field_record.py --class vehicular --site roadside --minutes 15
python noise_logger.py --site home_garage --site-id N01 --url https://noisemonitoringsystem.pythonanywhere.com
python live_monitor.py --site-id N02 --url https://noisemonitoringsystem.pythonanywhere.com
```

Only one of these programs can use the microphone at a time.

Thesis tables and figures are written to `data/results/`:

```bash
python thesis_results.py && python thesis_figures.py
python thesis_chaos.py
python thesis_site_levels.py
python thesis_forecast.py      # needs the logger readings in data/logging/, which are not in this repository
```

## Getting started

Use Python 3.11, then install the packages:

```bash
pip install -r requirements.txt
```

Keep `scikit-learn` at the listed version so the saved models load correctly.

## GIS dashboard

Live site: https://noisemonitoringsystem.pythonanywhere.com

```bash
python software/dashboard/server.py
```

- http://localhost:8000 is the public noise map.
- http://localhost:8000/admin.html is the staff dashboard.

See [software/dashboard/README.md](software/dashboard/README.md) for the features, staff accounts and how to connect the Raspberry Pi.
