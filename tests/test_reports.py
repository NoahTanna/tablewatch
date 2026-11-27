from datetime import date, datetime

from fastapi.testclient import TestClient

from backend import reports
from backend.app import create_app

FLOOR = [{"id": "T1", "name": "1", "seats": 2}, {"id": "T2", "name": "2", "seats": 4}]
DAY = date(2026, 11, 27)


def at(h, m=0, day=27):
    return datetime(2026, 11, day, h, m).timestamp()


def visit(tid, seat, leave, first=300, empty=None, cleared=None, red=False):
    return {"table_id": tid, "seated_at": seat, "left_at": leave, "first_service": first,
            "empty_before": empty, "cleared_at": cleared, "went_red": red}


def test_service_day_runs_past_midnight():
    assert reports.service_day(at(23, 30)) == DAY
    assert reports.service_day(datetime(2026, 11, 28, 0, 30).timestamp()) == DAY
    assert reports.service_day(datetime(2026, 11, 28, 5, 0).timestamp()) == date(2026, 11, 28)


def test_night_report_numbers():
    vs = [
        visit("T1", at(18), at(19), first=240, cleared=at(19, 2)),
        visit("T1", at(19, 10), at(20, 10), first=900, empty=480, cleared=at(20, 20), red=True),
        visit("T2", at(18, 30), at(20), first=None, cleared=None),
        visit("T2", at(20, 5), at(20, 6)),  # staff at the table for a minute: ignored
    ]
    r = reports.night(vs, DAY, FLOOR, not_served_after=600)
    assert r["parties"] == 3 and r["turns_per_table"] == 1.5
    assert r["avg_stay"] == (3600 + 3600 + 5400) / 3
    assert r["avg_first_service"] == (240 + 900) / 2
    assert r["late_starts"] == 2                         # 15 min and never served
    assert r["avg_clear_wait"] == (120 + 600) / 2 and r["went_red"] == 1
    assert r["worst_clear_wait"]["table"] == "1" and r["worst_clear_wait"]["seconds"] == 600
    assert r["idle_table_time"] == 120 + 600 + 480
    assert round(r["extra_parties_estimate"], 3) == round(1200 / r["avg_stay"], 3)
    assert [h["hour"] for h in r["busy_hours"]] == [18, 19, 20]
    assert r["busy_hours"][0]["busy"] == 0.75            # T1 all hour, T2 half: 1.5 of 2 tables
    t1 = next(t for t in r["tables"] if t["table"] == "1")
    assert t1["parties"] == 2 and t1["went_red"] == 1


def test_empty_night():
    r = reports.night([], DAY, FLOOR, 600)
    assert r["parties"] == 0 and r["avg_stay"] is None and r["busy_hours"] == [] and r["worst_clear_wait"] is None


def test_week_report():
    by_day = {date(2026, 11, d): [] for d in range(21, 28)}
    by_day[DAY] = [visit("T1", at(18), at(19), cleared=at(19, 10), red=True)]
    w = reports.week(by_day, FLOOR, 600)
    assert len(w["nights"]) == 7 and w["nights"][-1]["short"] == "Fri"
    assert w["parties"] == 1 and w["went_red"] == 1 and w["slowest_clearing_night"] == "Friday, Nov 27"
    assert w["nights"][-1]["busiest_hour"] == 18


def test_report_endpoints(tmp_path):
    import json
    floor = tmp_path / "floor.json"
    floor.write_text(json.dumps({"tables": [{"id": "T1", "name": "1", "seats": 2, "x": 1, "y": 1}]}))
    t = {"now": at(18)}
    app = create_app(str(tmp_path / "r.db"), str(floor), 3, clock=lambda: t["now"])
    c = TestClient(app)
    c.post("/api/events", json={"table_id": "T1", "people": True, "dishes": True, "dish_count": 3})
    t["now"] = at(18, 5)
    c.post("/api/events", json={"table_id": "T1", "people": True, "dishes": True, "dish_count": 6})
    t["now"] = at(19)
    c.post("/api/events", json={"table_id": "T1", "people": False, "dishes": True, "dish_count": 6})
    t["now"] = at(19, 4)
    app.state.run_tick()                                 # went red after 3 min
    c.post("/api/tables/T1/clear")
    r = c.get("/api/reports/night").json()
    assert r["day"] == "2026-11-27" and r["parties"] == 1
    assert r["avg_first_service"] == 300 and r["went_red"] == 1 and r["avg_clear_wait"] == 240
    w = c.get("/api/reports/week?end=2026-11-27").json()
    assert w["parties"] == 1 and len(w["nights"]) == 7
    assert c.get("/api/reports/night?day=2026-11-26").json()["parties"] == 0
