# TableWatch

A live screen on an iPad at the host stand, driven by the dining-room camera. Two views of the same tables: a **Map** of the room, where a ring around each table fills as the meal goes on, and a **List** of lanes sorted by what to do (Clear now, Needs service, Eating, Wrapping up, Open). Light by default; staff can switch to **Dark**. The iPad remembers both choices. To force them, add `?view=list` or `?theme=dark` to the address. It is **quiet by design**: only two things raise a banner and a soft chime, because those are the two things staff can act on right now.

| Tile | Meaning | Sound? |
|---|---|---|
| **Red, CLEAR + timer** | Guests left dishes behind and nobody has been to the table for 3 min. Tap it once it's cleared. | Banner + chime |
| **Orange, WAITING** | Guests sat down and nothing has arrived or been taken away for 10 min. Tap it once someone has been there. | Banner + chime |
| Just seated / Eating / Plates gone | Meal stage, with minutes since they sat (ring around the table on the map) | Silent |
| Dashed outline, Guests left | Guests are gone, dishes still there (turns red after 3 min) | Silent |
| Green, Free | Ready to seat. After a turn it shows how long it's been empty | Silent |
| *check?* chip | Plates gone for 10 min, guests still sitting: maybe waiting for the check (a hint; the camera is weakest here) | Silent |
| *long stay* chip | Seated much longer than tonight's typical party (90 min until there's enough data) | Silent |

A third tab, **Reports**, covers the end of the night and the week. All of it is worked out from table times only, with no per-server numbers:
- parties seated and turns per table;
- typical meal length;
- time to first service, and how many tables waited past the "nothing served" alert;
- how long dirty tables waited to be cleared, and how many went red;
- table time not earning (dirty plus empty), with a rough "about N more parties" estimate;
- how full the room was hour by hour;
- a by-table breakdown.

The week view compares the last 7 nights; tap a night to open it. A night runs 4 AM to 4 AM, so late tables count toward the evening they started. To try it with made-up history: `python tools/sample_history.py demo.db`, then `./dev.sh demo`. Never run that on a real restaurant's database.

The header shows how full the room is (tables and seats) and tonight's averages: time from sitting down to first service, and empty time between parties. A freshly set table with clean glasses stays green. There are no per-server numbers. Why these features: see [docs/research.md](docs/research.md).

```
IP camera --RTSP--> edge agent (mini PC) --people/dishes per table--> backend --live updates--> iPad dashboard
```

The edge agent sends only `table_id`, two yes/no values (people, dishes) and a dish count. No video, images or audio leave it or get stored.

To hear the chime, tap **Sound off** once at the start of each shift. iPad Safari only plays sound after a tap.

## 1. Try it without a camera

Requires Python 3.10+.

```bash
./dev.sh demo   # backend + dashboard + a simulated dinner service, every timer shortened to seconds
./dev.sh        # backend + dashboard only, real timers
```

Open http://localhost:8000. Tests: `.venv/bin/pytest -q`

Settings (environment variables, in minutes; on the mini PC, put them in `deploy/tablewatch-backend.service`):

| Variable | Default | What it controls |
|---|---|---|
| `CLEAR_AFTER_MIN` | 3 | guests gone, dishes left: turns red after this |
| `NOT_SERVED_MIN` | 10 | seated, nothing arrived or removed: turns orange after this |
| `PLATES_GONE_MIN` | 3 | plates gone this long before the tile says PLATES GONE |
| `CHECK_HINT_MIN` | 10 | plates gone this long before the *check?* chip |
| `LONG_STAY_MIN` | 90 | *long stay* threshold until 5 parties have finished tonight (then 1.5× the median stay) |
| `MIN_VISIT_MIN` | 2 | shorter "visits" (staff at the table) are left out of tonight's averages |

Also: `PORT` (8000), `TABLEWATCH_DB` (`tablewatch.db`; demo mode uses `demo.db`), `TABLEWATCH_FLOOR` (`config/floor.json`).

`docs/demo.html` is the real dashboard plus a stand-in server that plays a sped-up dinner service, all in one file that runs in any browser. Rebuild it after changing the dashboard: `python tools/build_demo.py`.

The floor map comes from `config/floor.json`: each table's position (% of the room), shape (`round`, `square`, `booth`, `rect`), seats and section, plus optional landmarks like the bar and the host stand.

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
| `--conf` | confidence needed to count a person | 0.35 |
| `--dish-conf` | confidence needed to count a dish | 0.25 |

The agent looks for people in the whole frame and for dishes in a zoomed crop of each table, because dishes far from the camera are tiny. That's one model run per table per sample, about 0.2 s each on a 4-core CPU. With many tables, raise `--every`.

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
| POST | `/api/events` | Edge report: `{"table_id": "T1", "people": false, "dishes": true, "dish_count": 4}` (count optional) |
| GET  | `/api/tables` | Every table with its stage, alert and hints, the room summary, and when the camera last reported |
| GET  | `/api/stream` | Server-Sent Events: one message for each table change |
| POST | `/api/tables/{id}/clear` | Staff marked the table cleared, so it becomes FREE |
| POST | `/api/tables/{id}/served` | Staff confirmed someone has been to a WAITING table |
| GET  | `/api/reports/night?day=YYYY-MM-DD` | One night's report (default: tonight) |
| GET  | `/api/reports/week?end=YYYY-MM-DD` | The 7 nights ending on that day |
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
- **Tested on real restaurant footage, not yet on your restaurant.** On a free time-lapse filmed from a fixed high camera (`eval/mixkit-4385/`), the detector got people right 92% of the time (it missed none) and dishes right 97% of the time (no phantom dishes). Plates with food are detected. The model has no "plate" class, so bare empty plates may still be missed. Lighting, camera angle and your tableware will change these numbers, so measure on your own footage in step 2.
- **Camera placement matters.** In the real-footage test, a single cup about 15 pixels wide at the far end of a 720p view was missed after video compression. Use a 1080p or better camera, mounted high and as close to the tables as practical.
- Zones matter: when the camera looks down at an angle, guests overlap the neighboring tables. Each person counts only for the table whose zone covers most of them, so draw zones carefully where tables are close together.
- No login: anyone on the restaurant network can post events or clear tables. Keep it on a private network.
- Plain HTTP on the local network.
