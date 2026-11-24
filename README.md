# TableWatch (MVP)

Shows live table status at the host stand: **green = FREE**, **gray = SEATED**, **red = NEEDS CLEARING**.
Red means dishes are on the table and nobody has been there for N minutes (default 3). Tap a red table once it has been cleared.

Milestone 1 has no camera yet. A simulator plays the role of the edge agent.

## Run

Requires Python 3.10+.

```bash
./dev.sh demo   # backend + dashboard + simulator, N = 30 s so red tables show up quickly
./dev.sh        # backend + dashboard only, N = 3 min
```

The first run creates `.venv` and installs dependencies. Open http://localhost:8000.

Settings (environment variables): `CLEAR_AFTER_MIN` (default 3), `PORT` (default 8000),
`TABLEWATCH_DB` (default `tablewatch.db`; demo mode uses `demo.db`), `TABLEWATCH_FLOOR` (default `config/floor.json`).

Tests: `.venv/bin/pytest -q`

## Open it on an iPad (same Wi-Fi)

1. Find the computer's local IP address: macOS `ipconfig getifaddr en0`, Linux `hostname -I`, Windows `ipconfig`. It looks like `192.168.1.23`.
2. In Safari on the iPad, go to `http://192.168.1.23:8000`.
3. Full screen: Share → **Add to Home Screen**, then open "Tables" from the home screen.
4. Keep the screen on: Settings → Display & Brightness → Auto-Lock → Never. Use Guided Access to lock the iPad to the app.

If the page doesn't load, the computer's firewall is probably blocking port 8000 (macOS will ask the first time), or the guest Wi-Fi is isolating devices from each other.

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/events` | Edge agent report: `{"table_id": "T1", "people": false, "dishes": true}` |
| GET  | `/api/tables` | Current state of all tables |
| GET  | `/api/stream` | Server-Sent Events: one message for each table change |
| POST | `/api/tables/{id}/clear` | Staff marked the table cleared, so it becomes FREE |
| GET  | `/api/floor` | Floor layout (from `config/floor.json`) |

The edge agent sends two booleans per table. It never sends images. The backend owns the N-minute timer.

## Layout

```
backend/state.py   pure state logic (the rules)
backend/db.py      SQLite, one row per table
backend/app.py     FastAPI endpoints + SSE
dashboard/         static page (plain HTML/JS/CSS)
config/floor.json  tables: id, name, x/y (% of floor), shape, seats
config/zones.json  detection polygons per table (used by the edge agent from Milestone 2)
simulator.py       fake edge agent for demos
```

## Known limits

- No authentication. Anyone on the network can post events or clear tables. This is fine on a private LAN but has to be fixed before a real deployment.
- Plain HTTP on the LAN.
