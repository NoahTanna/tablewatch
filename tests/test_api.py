import json
import socket
import threading
import time

import httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient

from backend.app import create_app


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


@pytest.fixture
def floor_path(tmp_path):
    p = tmp_path / "floor.json"
    p.write_text(json.dumps({"tables": [
        {"id": "T1", "name": "1", "x": 10, "y": 10, "shape": "round", "seats": 2},
        {"id": "T2", "name": "2", "x": 50, "y": 10, "shape": "square", "seats": 4},
    ]}))
    return str(p)


@pytest.fixture
def setup(tmp_path, floor_path):
    clock = Clock()
    app = create_app(str(tmp_path / "t.db"), floor_path, clear_after_min=3, clock=clock)
    return TestClient(app), app, clock


def states(client):
    return {t["id"]: t["state"] for t in client.get("/api/tables").json()["tables"]}


def test_initial_state_all_free(setup):
    client, _, _ = setup
    assert states(client) == {"T1": "FREE", "T2": "FREE"}


def test_event_updates_state(setup):
    client, _, _ = setup
    r = client.post("/api/events", json={"table_id": "T1", "people": True, "dishes": True})
    assert r.status_code == 200 and r.json()["state"] == "OCCUPIED"
    assert states(client)["T1"] == "OCCUPIED"


def test_unknown_table_404(setup):
    client, _, _ = setup
    r = client.post("/api/events", json={"table_id": "NOPE", "people": True, "dishes": False})
    assert r.status_code == 404
    assert client.post("/api/tables/NOPE/clear").status_code == 404


def test_bad_payload_422(setup):
    client, _, _ = setup
    assert client.post("/api/events", json={"table_id": "T1"}).status_code == 422


def test_needs_clearing_after_n_minutes_then_cleared(setup):
    client, app, clock = setup
    client.post("/api/events", json={"table_id": "T1", "people": True, "dishes": True})
    client.post("/api/events", json={"table_id": "T1", "people": False, "dishes": True})
    clock.t += 179
    app.state.run_tick()
    assert states(client)["T1"] == "OCCUPIED"
    clock.t += 1
    app.state.run_tick()
    assert states(client)["T1"] == "NEEDS_CLEARING"
    r = client.post("/api/tables/T1/clear")
    assert r.json()["state"] == "FREE"
    assert states(client)["T1"] == "FREE"


def test_state_persists_across_restart(tmp_path, floor_path):
    db = str(tmp_path / "p.db")
    c1 = TestClient(create_app(db, floor_path, 3))
    c1.post("/api/events", json={"table_id": "T2", "people": True, "dishes": False})
    c2 = TestClient(create_app(db, floor_path, 3))
    assert states(c2)["T2"] == "OCCUPIED"


def test_floor_and_dashboard_served(setup):
    client, _, _ = setup
    assert [t["id"] for t in client.get("/api/floor").json()["tables"]] == ["T1", "T2"]
    assert "TableWatch" in client.get("/").text
    assert client.get("/static/app.js").status_code == 200


def test_sse_stream_pushes_updates(tmp_path, floor_path):
    """Run a real server, subscribe to the stream, post an event, expect it on the stream."""
    app = create_app(str(tmp_path / "s.db"), floor_path, 3)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    for _ in range(50):
        if server.started:
            break
        time.sleep(0.1)
    try:
        with httpx.Client(timeout=5) as c, c.stream("GET", base + "/api/stream") as s:
            assert s.headers["content-type"].startswith("text/event-stream")
            lines = s.iter_lines()
            assert next(lines).startswith("retry:")
            c.post(base + "/api/events", json={"table_id": "T2", "people": True, "dishes": True})
            msgs = (json.loads(l[5:]) for l in lines if l.startswith("data:"))
            msg = next(m for m in msgs if m["table"]["id"] == "T2" and m["table"]["state"] == "OCCUPIED")
            assert msg["table"]["stage"] == "SEATED" and msg["summary"]["tables_in_use"] == 1
    finally:
        server.should_exit = True


def test_last_event_at_tracks_camera(setup):
    client, _, clock = setup
    assert client.get("/api/tables").json()["last_event_at"] is None
    client.post("/api/events", json={"table_id": "T1", "people": False, "dishes": False})
    assert client.get("/api/tables").json()["last_event_at"] == clock.t


def ev(client, tid, people, dishes, count=None):
    return client.post("/api/events", json={"table_id": tid, "people": people, "dishes": dishes,
                                             "dish_count": count})


def test_summary_fullness_and_tonight(tmp_path, floor_path):
    clock = Clock()
    app = create_app(str(tmp_path / "s.db"), floor_path, 3, clock=clock)
    client = TestClient(app)
    s = client.get("/api/tables").json()["summary"]
    assert (s["tables_in_use"], s["tables_total"], s["seats_in_use"], s["seats_total"]) == (0, 2, 0, 6)
    ev(client, "T2", True, True, 3)
    s = client.get("/api/tables").json()["summary"]
    assert (s["tables_in_use"], s["seats_in_use"]) == (1, 4)
    clock.t += 240
    ev(client, "T2", True, True, 6)                       # served after 4 min
    clock.t += 1800
    ev(client, "T2", False, False, 0)                     # left and bussed
    s = client.get("/api/tables").json()["summary"]
    assert s["visits_tonight"] == 1 and s["avg_first_service"] == 240
    clock.t += 300
    ev(client, "T2", True, True, 3)                       # next party after 5 empty minutes
    clock.t += 600
    ev(client, "T2", False, False, 0)
    assert client.get("/api/tables").json()["summary"]["avg_empty_between"] == 300


def test_not_served_alert_then_served_tap(setup):
    client, app, clock = setup
    ev(client, "T1", True, True, 3)
    clock.t += 601
    app.state.run_tick()
    t1 = next(t for t in client.get("/api/tables").json()["tables"] if t["id"] == "T1")
    assert t1["alert"] == "not_served"
    r = client.post("/api/tables/T1/served")
    assert r.json()["alert"] is None and r.json()["stage"] == "SERVED"


def test_old_style_events_without_count_still_work(setup):
    client, _, _ = setup
    r = client.post("/api/events", json={"table_id": "T1", "people": True, "dishes": True})
    assert r.json()["stage"] == "SEATED"
