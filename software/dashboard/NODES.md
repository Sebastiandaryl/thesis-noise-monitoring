# Adding phone and laptop nodes (5 nodes for the defense)

The Raspberry Pi is node 1. Phones and laptops can be nodes 2 to 5. Each one uses **its own microphone**, and its clips go through **the same pipeline as the Pi**: calibrated A-weighted dB, the same features, the same YAMNet + ensemble model, the same 15-minute forecast.

## How it works (the short version)

```
 Phone / laptop  ──5 s clip + dB──►  Dashboard (PythonAnywhere)  ◄──asks for clips──  Hub (Pi or a laptop)
   node.html                          stores it, shows it on map  ──finished reading──►  runs the classifier
```

1. **Each phone or laptop** opens a web page, `node.html`. It listens with the microphone, works out the loudness in dB(A), and sends each 5-second clip to the dashboard.
2. **One computer is the "hub".** It runs `node_hub.py`. It picks up the clips, figures out what kind of noise it is (vehicular, human, …) with the same model as the Pi, and sends the answer back to the map.
3. If the hub is off, the map still gets the dB level from every node, just without the noise type.

Nothing needs to be installed on the phones. Only the hub needs Python.

## What you need

- The Raspberry Pi running as usual (`live_monitor.py --site-id N02 --url ...`).
- 4 phones and/or laptops with a working microphone and internet.
- One hub computer: the Pi itself, or a laptop with the thesis Python packages (`pip install -r requirements.txt`). A laptop is faster and leaves the Pi free; use one if you can.
- Something to play steady noise (any phone or laptop speaker works, the page has a button).
- Optional: a sound level meter, or a sound meter app (NIOSH SLM on iPhone is a good free one).

## Step 1 · Update the dashboard (once)

On PythonAnywhere, open **Consoles → Bash** and run:

```bash
cd ~/thesis-noise-monitoring && git pull
```

Then go to the **Web** tab and click the green **Reload** button. Check that this opens:
`https://noisemonitoringsystem.pythonanywhere.com/node.html`

## Step 2 · Start the hub

On the hub computer, in the thesis folder:

```bash
cd software/processing
python node_hub.py --url https://noisemonitoringsystem.pythonanywhere.com --chaos
```

Leave this window open. It prints one line for every clip it classifies. (`--chaos` also sends λ, D₂ and Df for each node to the staff dashboard. Leave it out if the hub is slow.)

> If `--chaos` fails with `No module named 'pkg_resources'`, run `pip install "setuptools<81"` once.
> If the hub is the Pi, run it in its own tmux window next to `live_monitor.py`.

## Step 3 · Open the node page on each phone or laptop

On every phone or laptop, open in **Chrome** (or Safari on iPhone):

```
https://noisemonitoringsystem.pythonanywhere.com/node.html
```

Fill in **1 · Name this node**:

| Device | Node ID | Name on the map (example) |
|---|---|---|
| Raspberry Pi | N02 (already set) | DLSU Velasco Hall · Defense room |
| Phone or laptop #1 | N03 | Velasco lobby · Ana's phone |
| Phone or laptop #2 | N04 | Hallway · Ben's laptop |
| Phone or laptop #3 | N05 | Stairs · Carl's phone |
| Phone or laptop #4 | N06 | Outside · Dana's phone |

**Every device must have a different Node ID.** Pick Phone or Laptop under *Device*.

**Location**: phones can use their own GPS. Laptops usually only know a rough Wi-Fi location, so choose **Type the coordinates myself** and type the spot (right-click the place on Google Maps to copy its latitude, longitude). Put the nodes in **different spots** (rooms, hallway, outside). If they all sit on one table, their pins stack on top of each other on the map.

Tip: you can make a link that fills in the ID and name for you, for example
`.../node.html?id=N03&name=Velasco%20lobby`

## Step 4 · Calibrate every microphone

Every microphone hears loudness differently. Calibrating makes all of them agree with one reference.

**The reference is the Raspberry Pi.** Its INMP441 microphone has a factory sensitivity from its datasheet (−26 dBFS at 94 dB SPL), so it is our "ruler". If you have a sound meter app, check the Pi against it first (see the end of this step).

Do this for all 4 devices together:

1. Make sure the Pi is running and sending (you can see N02 on the map).
2. Put all the phones and laptops **right next to the Pi**, microphones the same distance (about 30–50 cm) from the speaker.
3. On one extra phone or laptop (not one being calibrated), open `node.html` and press **Play test noise on this device**. Turn the volume up until it's about as loud as a busy street (70–80 dB). It should sound like a steady "shhhh".
4. On every node, under **2 · Calibrate**, keep *Reference* on **The Raspberry Pi on the map**, check the reference ID is `N02`, and press **Measure (15 s)** at about the same time. Don't talk or move.
5. Each page says **Done** and shows its new offset. The badge turns green: **Calibrated**.
6. Stop the test noise.

**Check it:** play the noise again for a few seconds. *Level now* on every device should be within about 2 dB of the Pi. If one is off, press Measure again on that one.

The offset is saved on that device in that browser, so you only calibrate again if you change the browser or the device.

**No Pi nearby?** Choose **A number I read from a sound meter**, put the sound meter app next to the device, play the noise, type the meter's dB(A) number, and press Measure.

**Calibrating the Pi too (optional, if you have a sound meter):** play the noise next to the Pi and the meter. If the Pi reads, say, 73.0 and the meter says 75.0, the Pi is 2 dB low. Restart it with the offset raised by 2:

```bash
python live_monitor.py --site-id N02 --url https://noisemonitoringsystem.pythonanywhere.com --cal-offset 122
```

(The normal value is 120. Then calibrate the phones and laptops against the Pi again.)

## Step 5 · Start every node

1. Plug each phone or laptop into a charger.
2. Press **Start sensor**. Allow the microphone and location when the browser asks.
3. Keep the page open with the **screen on**. If a phone locks its screen, the microphone stops.

The page shows:

| Box | What it means |
|---|---|
| Level now | Loudness this second, in dB(A) |
| Last reading on the map | What the dashboard has for this node, with the noise type from the classifier |
| Sending | **Sent for classifying** = the hub is on. **Sent (level only)** = the hub is off |
| Classifier | Whether the hub is running |

Open the dashboard (`/` or `/admin.html`): all 5 nodes appear on the map within about 10 seconds. New node IDs appear on their own at their location. In the staff dashboard you can rename them or drag them to a better spot under **Sensor nodes**.

## If something goes wrong

| Problem | Fix |
|---|---|
| "Could not open the microphone" | Use the `https://` address (not `http://`), allow the microphone, and close other apps using it (Zoom, voice recorder). |
| Classifier says "Not running" | Start `node_hub.py` (Step 2) and check its window for errors. |
| Node not on the map | It needs a location. Allow location, or choose *Type the coordinates myself*. |
| "No readings from N02 during the measurement" | The Pi isn't sending. Start `live_monitor.py --url ...` on the Pi, or calibrate with a sound meter number. |
| All the pins are on top of each other | Move the devices to different places, or type different coordinates. |
| Phone readings stop | The screen turned off or the page went to the background. Keep it open and the screen on. |
| "wrong device key" | The server has `NMA_DEVICE_KEY` set. Type the same key under *More settings* on each node, and `export NMA_DEVICE_KEY=...` before starting the hub. |

## What to tell the panel

- All 5 nodes use **their own microphone**. Each phone or laptop computes the **A-weighted LAeq** the same way as the Pi (FFT A-weighting, IEC 61672), and the hub recomputes it in Python with the device's calibration offset.
- Classification uses **the exact same model and features** as the Pi (handcrafted features + YAMNet embeddings → SVM + YAMNet ensemble), with the same quiet-level rule (below 40 dB(A) = ambient) and the same 15-minute forecast.
- Every phone and laptop was **calibrated against the Pi's INMP441** (datasheet sensitivity) with steady pink noise, so all nodes share one reference. Echo cancellation, noise suppression and automatic gain are turned off in the browser so the phone doesn't change the loudness.
- Limits to be honest about: phone and laptop mics have a different frequency response from the INMP441, and the model was trained on INMP441 recordings, so classification on phones may be a little less accurate than on the Pi. A one-point calibration fixes the overall level, not the frequency response.
