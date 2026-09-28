# GIS noise dashboard

A single-page web dashboard for the noise monitoring network. It shows a noise map of the sensor sites, measured vs predicted levels, noise source classification, chaos metrics and alerts.

It runs on placeholder data today. When the prototype is ready, the Raspberry Pi posts its readings to a small server and the dashboard shows them live. The dashboard code itself does not need to change.

## Run it

```bash
python software/dashboard/server.py
```

Open http://localhost:8000. From another device on the same network, use the Pi's address, for example `http://raspberrypi.local:8000`.

Opening `index.html` directly in a browser also works, but only in simulated mode.

## What's on the dashboard

- **Noise map** (Leaflet): one marker per site, colored by noise level band. You can switch between measured and predicted (+15 min) values and turn on a heatmap layer and high-risk zone rings (sites whose 1-hour LAeq is 70 dB or more). Basemaps are OpenStreetMap, CARTO light/dark and Esri satellite, plus an offline schematic of the Taft/Malate area.
- **24-hour replay**: scrub or play back the map over the last day.
- **Filters**: by dominant noise source (vehicular, industrial, human activity, commercial, ambient), by minimum level, or only sites above the WHO limit.
- **Summary strip**: network LAeq, loudest site, sites above the WHO limit (55 dB day, 40 dB night), active alerts, forecast error (MAE) and nodes online.
- **Site panel**: measured and predicted level, LAeq/Lmax/L10/L90 for the last hour, classifier probabilities, and chaos metrics (Lyapunov λ, correlation dimension D₂, fractal dimension Df).
- **Charts**: measured vs predicted (1 h / 6 h / 24 h), hourly profile against the WHO limits, noise source mix per site, and a phase-space portrait (delay embedding) of the selected site.
- **Sensor table** (sortable), **alerts feed** (warning at 70 dB, critical at 85 dB, forecast exceedance, node offline), **classifier comparison** table, and **Copy CSV**.

Light and dark themes follow the system setting. The layout works on phones.

## Connect the prototype

1. Start the server on the central Pi: `python software/dashboard/server.py`.
2. In the recording loop, compute the level and send a reading:

   ```python
   from publish_reading import compute_laeq, send_reading

   audio = record_audio()
   laeq = compute_laeq(audio, TARGET_SR)      # raw audio, BEFORE peak normalization
   features = extract_features(audio)
   ...
   send_reading(
       site_id="S01",
       laeq_db=laeq,
       category=prediction,
       probabilities=dict(zip(model.classes_, probabilities)),
       # optional: predicted_db=..., lle=..., corr_dim=..., fractal_dim=...
   )
   ```

   `compute_laeq` applies A-weighting and assumes the INMP441 sensitivity (−26 dBFS at 94 dB SPL). After checking against a reference sound level meter, adjust `CALIBRATION_OFFSET_DB` in `publish_reading.py`.

3. In the dashboard, open **Data source**, choose **Prototype API (live)** and click **Apply**. To make live mode the default, set `DATA_MODE: "api"` in `CONFIG` near the top of the script in `index.html`.

To send a test reading without the microphone:

```bash
python software/processing/publish_reading.py --site S03 --db 81.2 --category commercial
```

### Reading format

`POST /api/readings` accepts one object or a list. Only `site_id` and `laeq_db` are required.

```json
{
  "site_id": "S01",
  "timestamp": "2026-09-28T22:15:03+08:00",
  "laeq_db": 71.4,
  "predicted_db": 73.0,
  "category": "vehicular",
  "probabilities": { "vehicular": 0.71, "commercial": 0.12, "human": 0.09, "ambient": 0.06, "industrial": 0.02 },
  "lle": 0.084,
  "corr_dim": 2.61,
  "fractal_dim": 1.52
}
```

`predicted_db` is the forecast for 15 minutes after `timestamp`. If your model uses a different horizon, change `FORECAST_HORIZON_MIN` in `CONFIG`. Category names match the classes in `extract_features.py`.

Readings are stored in `data/live/readings.jsonl` (ignored by git), so the charts keep their history after a restart.

## Things to replace before the defense

| What | Where |
|---|---|
| Real site coordinates and names | `SITES` in `index.html` (or send `lat`, `lng`, `name` with each reading) |
| Classifier results | `MODEL_RESULTS` in `index.html` |
| Alert thresholds, WHO limits, day/night hours | `CONFIG` in `index.html` |

Site IDs in `SITES` must match the `site_id` each Pi sends.
