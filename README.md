# TableWatch

Shows live table status on an iPad at the host stand: **green = FREE**, **gray = SEATED**, **red = NEEDS CLEARING**.
Red means dishes are on the table and nobody has been there for N minutes (default 3). Tap a red table once it has been cleared.

```
IP camera --RTSP--> edge agent (mini PC) --people/dishes per table--> backend --live updates--> iPad dashboard
```

The edge agent sends only `table_id` + two yes/no values. No video, images or audio leave it or get stored.

## 1. Try it without a camera

Requires Python 3.10+.

```bash
./dev.sh demo   # backend + dashboard + simulated tables, N = 30 s so red tables show up quickly
./dev.sh        # backend + dashboard only, N = 3 min
```

Open http://localhost:8000. Tests: `.venv/bin/pytest -q`

`docs/demo.html` is a standalone copy of the dashboard that runs in any browser with no server, for showing the idea.

### Open it on an iPad (same Wi-Fi)

1. Find the computer's local IP: macOS `ipconfig getifaddr en0`, Linux `hostname -I`, Windows `ipconfig` (e.g. `192.168.1.23`).
2. In Safari on the iPad open `http://192.168.1.23:8000`.
3. Full screen: Share → **Add to Home Screen**, then open "Tables" from the home screen.
4. Keep it on: Settings → Display & Brightness → Auto-Lock → Never. Guided Access locks the iPad to the app.

If it doesn't load: the computer's firewall is blocking port 8000, or the Wi-Fi isolates devices (common on guest networks).

## 2. Test detection on recorded video

Do this before going live, with a recording from your own camera of a real service.

```bash
.venv/bin/pip install -r requirements-edge.txt
./edge/get_model.sh
```

**Draw table zones (one time).**

1. Save one still of the room, ideally when it's empty: `python -m edge.snapshot --source dinner.mp4 --out room.jpg`
   This is the only step that writes an image to disk. Delete `room.jpg` when you're done.
2. Open `tools/zone_editor.html` in a browser and load `room.jpg`. For each table, type its id (matching `config/floor.json`), click around the table **and its chairs**, then press "Finish zone".
3. Paste the JSON into `config/zones.json`.

**Run the detector on the video.**

```bash
python -m edge.agent --source dinner.mp4 --dry-run --log predictions.csv
```

**Label the truth by hand** in `labels.csv`, adding one row each time something changes at a table. Give every table a row at time 0:

```
time_s,table_id,people,dishes
0,T1,1,1
1260,T1,0,1
1500,T1,0,0
```

**Score it:**

```bash
python -m edge.evaluate labels.csv predictions.csv
```

The score shows, for each table:
- how often "people" and "dishes" were right
- how many real "needs clearing" moments were caught
- false alarms
- the average delay

Settings worth tuning:

| Flag | What it does | Default |
|---|---|---|
| `--every` | seconds between sampled frames | 3 |
| `--confirm` | samples in a row before a change counts (filters out waiters walking past) | 3 |
| `--conf` | detector confidence threshold | 0.35 |

## 3. Go live on a mini PC

Use any small Ubuntu or Debian PC on the restaurant network, for example an Intel N100 box. It runs both the backend and the edge agent.

```bash
git clone https://github.com/NoahTanna/tablewatch && cd tablewatch
sudo ./deploy/install.sh
sudo nano /etc/tablewatch/edge.env                     # put the camera's RTSP address here
sudo nano /opt/tablewatch/config/floor.json            # your tables
sudo nano /opt/tablewatch/config/zones.json            # zones from step 2
sudo systemctl restart tablewatch-backend tablewatch-edge
```

Then open `http://<mini-pc-ip>:8000` on the iPad. Both services start on boot and restart if they crash. If the camera stream drops, the agent keeps retrying. If the screen gets no camera data for 2 minutes, it shows a warning so staff know the colors may be stale.

Logs: `journalctl -u tablewatch-edge -f`

One agent watches one camera. For a second camera, run a second agent with its own zones file.

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/events` | Edge report: `{"table_id": "T1", "people": false, "dishes": true}` |
| GET  | `/api/tables` | Current state of all tables, plus when the camera last reported |
| GET  | `/api/stream` | Server-Sent Events: one message for each table change |
| POST | `/api/tables/{id}/clear` | Staff marked the table cleared, so it becomes FREE |
| GET  | `/api/floor` | Floor layout |

## Layout

```
backend/        FastAPI + SQLite; state.py holds the rules
dashboard/      iPad page (plain HTML/JS/CSS)
edge/           detector, zones, debounce, agent, evaluate, snapshot
config/         floor.json (dashboard map), zones.json (camera polygons)
tools/          zone_editor.html
deploy/         install.sh + systemd services for the mini PC
simulator.py    fake edge agent for demos
```

## Licenses and known limits

- Dependencies:
  - Server: FastAPI (MIT), uvicorn (BSD).
  - Edge: onnxruntime (MIT), numpy (BSD), opencv-python-headless (Apache-2.0; bundles FFmpeg, LGPL, as a separate library).
  - Model: YOLOX-s (Apache-2.0).
  - No AGPL. The model was trained on COCO; have counsel confirm that's fine for your commercial use.
- **The model has no "plate" class.** "Dishes" means cups, glasses, bowls, bottles, cutlery and common foods. A bare empty plate may be missed. Measure this on real footage in step 2. If it matters, the fix is fine-tuning on labeled frames from your own restaurant.
- No login: anyone on the restaurant network can post events or clear tables. Keep it on a private network.
- Plain HTTP on the local network.
