# Manila Noise Atlas dashboard

The dashboard has two views of the same sensor data:

| Page | Who it's for | Sign-in |
|---|---|---|
| `index.html`, the public noise map | Residents, renters, home buyers, anyone planning their day | None |
| `admin.html`, the staff dashboard | **Administrators** (the research team) and **government planners** (LGU, DENR, DOH) | Required |

Both run on placeholder data today. When the prototype is ready, the Raspberry Pi posts its readings to `server.py` and both pages show them live. The page code does not need to change.

## Run it

```bash
# 1. Create the first administrator account (asks for a password)
python software/dashboard/server.py --add-user admin --role admin --name "Your Name"

# 2. Start the server
python software/dashboard/server.py
```

- Public map: http://localhost:8000
- Staff dashboard: http://localhost:8000/admin.html

From another device on the same network, use the Pi's address, for example `http://raspberrypi.local:8000`.

If you open the HTML files directly (double-click) or in the preview, there is no server. The staff page then runs in **demo mode**: sign in as `admin` / `admin123` or `planner` / `planner123`, and changes are saved only in that browser. Demo accounts never work when the pages are served by `server.py`.

## Put it online for free (PythonAnywhere)

This gives a fixed address like `https://yourname.pythonanywhere.com` that stays online without a computer of yours running. The Pi sends its readings there over the internet.

1. Sign up for a free **Beginner** account at pythonanywhere.com. Your username becomes the address, so pick something like `manilanoise`.
2. Open **Consoles → Bash** and run:
   ```bash
   git clone https://github.com/Sebastiandaryl/thesis-noise-monitoring.git
   python3 thesis-noise-monitoring/software/dashboard/server.py --add-user admin --role admin --name "Your Name"
   ```
3. Open the **Web** tab → **Add a new web app** → **Manual configuration** → the newest Python 3.
4. On the web app's page, click the **WSGI configuration file** link, delete everything in it, paste this (with your username) and click **Save**:
   ```python
   import sys
   sys.path.insert(0, "/home/YOURNAME/thesis-noise-monitoring/software/dashboard")
   from wsgi import application
   ```
5. Click the green **Reload** button and open `https://YOURNAME.pythonanywhere.com`.

Free web apps switch off after a month unless you log in and click **Run until 1 month from today** on the Web tab, so do that before the defense. To get code updates later: `cd thesis-noise-monitoring && git pull` in the Bash console, then **Reload**. Readings, accounts and notices are kept in `data/live/` on PythonAnywhere.

`wsgi.py` runs the same code as `server.py`, so everything below works the same either way.

## Defense demo (no hardware needed)

Open either page with `?demo` at the end of the address, for example `http://localhost:8000/admin.html?demo` or `index.html?demo` from a plain file. The browser then stays on sample readings, even if the server has real data, and every node reports a simulated GPS position. A **Demo preview** bar shows it's on. `?demo=off`, or the Exit demo button, turns it off.

On the staff page, the **Presentation demo** card lets you show what happens when:
- a node **loses its GPS fix**: it stays at its saved location and the GPS column says so;
- a node **goes offline**: an offline alert appears and the public page shows no live reading for it;
- there's a **loud noise event** for 2 minutes: the pin turns red and an alert fires.

Scenarios are saved in the browser, so a public-page tab next to the staff tab shows the same thing from a resident's view. **Reset all** puts every node back to normal.

## Maps

Both maps have a Google-style **Map | Satellite** switch in the corner. *Map* uses CARTO Voyager, which looks closest to Google Maps, or a dark map in dark mode. *Satellite* is Esri World Imagery with street names on top. The staff page also offers light grey, dark, OpenStreetMap and an **offline map**.

The map covers the whole Philippines (and the rest of the world online). Nodes are placed by their GPS latitude and longitude, wherever they are. The globe button under the zoom buttons shows the whole country, and the square button zooms to all nodes.

Without internet, both pages switch to the built-in **offline map of the Philippines** (`assets/ph-basemap.js`): the coastline of every major island from Natural Earth 1:10m, city names from GeoNames that appear as you zoom in, and a street sketch around DLSU. It has no street detail elsewhere, but every node still shows at its real position. `tools/build-ph-basemap.js` regenerates the file.

Real Google Maps tiles need a Google Cloud API key with billing enabled, so they're not included.

## Public noise map (`index.html`)

Plain language, no jargon. Everything a resident needs to decide whether an area suits them:

- **Notices** from the administrators at the top, for example "Pandacan sensor under maintenance".
- **Area picker and map**. You can color the map by **noise right now**, the **forecast for the next 15 minutes** (dashed pins), or **livability grade**. Sensors under maintenance are greyed out.
- **Area card**:
  - **Right now**: the level with an everyday comparison ("like heavy city traffic") and whether it's within the WHO guideline.
  - **Predicted in 15 min**: the forecast level and whether it's getting louder or quieter.
  - **Forecast accuracy**: the average difference between predicted and actual over the last 24 hours, and the share of forecasts within 3 dB.
  - **Living here**: a grade from A (quiet) to E (very noisy) with advice, plus day and night averages checked against the WHO guideline (55 dB day, 40 dB night).
  - **Facts**: the main source of noise in plain words (traffic, people, industry…), loudest and quietest hours, and the loudest moment in the past hour.
- **Predicted vs actual**: a chart of the measured level against the AI forecast (3 h, 12 h or 24 h, plus the next 15 minutes), a predicted-vs-actual scatter plot, and plain-language accuracy figures: average difference (MAE), % within 3 dB, whether it tends to predict too high or too low (bias), and the latest check.
- **A typical day**: 24 hourly blocks colored by loudness, so people can see when an area is calm.
- **Compare areas**: every area ranked quietest to loudest (or the reverse), with grade, level now and in 15 minutes, day and night averages, forecast accuracy and main source. Click one to open it.
- **What the numbers mean** (a dB scale with everyday examples) and **About this map** (how the data and grades work, a link for government staff).

The grade uses **Lden**, the day-evening-night level from the EU Environmental Noise Directive, over the last 24 hours. Evening readings (19:00–23:00) get a 5 dB penalty and night readings (23:00–07:00) a 10 dB penalty. A is under 55 dB, B 55–60, C 60–65, D 65–70, E 70 dB and above.

## Staff dashboard (`admin.html`)

Everything from the original dashboard: the noise map (heatmap, high-risk zones, measured/predicted, 24-hour replay), filters, summary strip, site panel with classifier probabilities and chaos metrics (λ, D₂, Df), measured vs predicted chart, phase-space portrait, 24-hour profile, source mix, sensor table, alerts and classifier comparison. It adds:

| Section | Administrator | Government planner |
|---|---|---|
| **Planning report**: grade, Lden, day/evening/night levels, % of time above the WHO day and night limits, main source per site. Copy as CSV. | ✓ | ✓ |
| **Sensor nodes**: add a node by clicking the map (**Add node on map**), move nodes by dragging their pins (**Drag nodes on map**), remove nodes, set Active, Maintenance or Offline with a note, and choose whether the location comes from **GPS** or is **Fixed**. The GPS column shows each node's live fix. | edit | view |
| **Presentation demo**: simulate GPS loss, an offline node or a noise event (see above) | ✓ | — |
| **Public notices**: post information, maintenance, noise warning or system problem notices, optionally for one area, with an expiry | post and remove | view |
| **Activity log**: sign-ins, failed sign-ins, notices, site changes and rejected readings | ✓ | ✓ |
| **Data source** settings | ✓ | — |

## Staff accounts

Accounts live in `data/live/users.json` (ignored by git). Passwords are stored as salted PBKDF2 hashes.

```bash
python software/dashboard/server.py --add-user admin --role admin --name "Daryl Sebastian"
python software/dashboard/server.py --add-user denr --role planner --name "DENR NCR"
python software/dashboard/server.py --list-users
python software/dashboard/server.py --remove-user denr
```

Sessions last 12 hours and use an HttpOnly, SameSite=Strict cookie. After 5 failed sign-ins from one address, that address must wait 10 minutes.

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

3. If the node has a GPS module (for example a NEO-6M on the Pi's serial port), pass its position:

   ```python
   from publish_reading import read_gps
   send_reading(..., gps=read_gps())
   ```

   `read_gps()` needs `pip install pyserial`. When there's no fix (indoors, module not connected), it sends `gps_fix: false` and the dashboard keeps the node at its **saved location**. The same happens if the fix is older than 5 minutes (`GPS_STALE_SEC` in `CONFIG`). Nodes without GPS just leave `gps` out.

4. That's it. With `DATA_MODE: "auto"` (the default in `CONFIG` in `assets/core.js`), both pages switch to live data as soon as the server has readings from the last 10 minutes.

To stop other devices on the network from posting fake readings, set the same secret on the server and on each Pi:

```bash
export NMA_DEVICE_KEY="some-long-random-text"
```

To send a test reading without the microphone:

```bash
python software/processing/publish_reading.py --site S03 --db 81.2 --category commercial
python software/processing/publish_reading.py --site S03 --db 81.2 --lat 14.5741 --lng 120.9967   # with a GPS position
python software/processing/publish_reading.py --site S03 --db 81.2 --no-fix                       # GPS without a fix
python software/processing/publish_reading.py --site S03 --db 81.2 --read-gps                     # read the real module
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
  "fractal_dim": 1.52,
  "lat": 14.56472,
  "lng": 120.99321,
  "gps_fix": true
}
```

`lat`, `lng` and `gps_fix` are optional. A reading with an unknown `site_id` and a GPS position adds that node to the map automatically.

`predicted_db` is the forecast for 15 minutes after `timestamp`. If your model uses a different horizon, change `FORECAST_HORIZON_MIN` in `CONFIG`. Category names match the classes in `extract_features.py`.

Everything the server stores is in `data/live/` (readings, accounts, notices, site changes, activity log) and is ignored by git.

## Files

```
software/dashboard/
├── index.html        public noise map
├── admin.html        staff dashboard
├── assets/
│   ├── core.js       settings, sites, simulator, data adapter, sign-in, grades, shared map
│   ├── core.css      colors, type and shared components (light and dark)
│   ├── ph-basemap.js offline map of the Philippines (coastline and cities)
│   └── leaflet.css   map library styles
├── server.py         pages, staff accounts and API (Python standard library only)
└── wsgi.py           the same server for WSGI hosts such as PythonAnywhere
```

## Things to replace before the defense

| What | Where |
|---|---|
| Real site coordinates and names | `DEFAULT_SITES` in `assets/core.js`, or edit them in the staff dashboard |
| Classifier results (empty until filled in; give the test split, ideally whole recordings held out) | `MODEL_RESULTS` in `assets/core.js` |
| Alert thresholds, WHO limits, day/night hours | `CONFIG` in `assets/core.js` |

Site IDs must match the `site_id` each Pi sends.
