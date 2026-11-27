"""TableWatch backend: receives table events, stores state, pushes live updates (SSE)."""
import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend import state
from backend.db import DB

ROOT = Path(__file__).resolve().parent.parent


TONIGHT_S = 8 * 3600  # averages cover the last 8 hours
MIN_VISITS_FOR_AVG = 5


class Event(BaseModel):
    """What the edge agent sees at one table. Never images: two booleans and a count."""
    table_id: str
    people: bool
    dishes: bool
    dish_count: int | None = None


def _minutes(name, default, override):
    value = override.get(name.lower()) if override else None
    return float(value if value is not None else os.environ.get(name, default))


def create_app(db_path=None, floor_path=None, clear_after_min=None, clock=time.time, settings=None):
    """settings: optional dict overriding the *_MIN environment variables (lowercase keys)."""
    db_path = db_path or os.environ.get("TABLEWATCH_DB", str(ROOT / "tablewatch.db"))
    floor_path = floor_path or os.environ.get("TABLEWATCH_FLOOR", str(ROOT / "config" / "floor.json"))
    if clear_after_min is None:
        clear_after_min = _minutes("CLEAR_AFTER_MIN", "3", settings)
    clear_after = clear_after_min * 60
    not_served_after = _minutes("NOT_SERVED_MIN", "10", settings) * 60
    check_hint_after = _minutes("CHECK_HINT_MIN", "10", settings) * 60
    long_stay_default = _minutes("LONG_STAY_MIN", "90", settings) * 60
    plates_gone_after = _minutes("PLATES_GONE_MIN", "3", settings) * 60
    min_visit = _minutes("MIN_VISIT_MIN", "2", settings) * 60  # shorter: staff at the table, not guests

    floor = json.loads(Path(floor_path).read_text())
    seats = {t["id"]: t.get("seats", 0) for t in floor["tables"]}
    db = DB(db_path)
    ids = [t["id"] for t in floor["tables"]]
    for tid in ids:
        db.ensure(state.new_table(tid))
    db.remove_except(ids)

    subscribers = set()  # one asyncio.Queue per connected dashboard
    last_event = {"at": None}  # when the camera side last reported (in memory)

    shown = {}  # table id -> what the dashboard was last sent

    def mean(xs):
        xs = [x for x in xs if x is not None]
        return sum(xs) / len(xs) if xs else None

    def summary(now, tables):
        visits = [v for v in db.visits_since(now - TONIGHT_S) if v["left_at"] - v["seated_at"] >= min_visit]
        stays = sorted(v["left_at"] - v["seated_at"] for v in visits)
        long_stay = long_stay_default
        if len(stays) >= MIN_VISITS_FOR_AVG:
            long_stay = 1.5 * stays[len(stays) // 2]
        seated = [t["id"] for t in tables if t["state"] == state.OCCUPIED and t["unattended_since"] is None]
        return {
            "tables_in_use": len(seated), "tables_total": len(tables),
            "seats_in_use": sum(seats.get(i, 0) for i in seated), "seats_total": sum(seats.values()),
            "avg_first_service": mean(v["first_service"] for v in visits),
            "avg_empty_between": mean(v["empty_before"] for v in visits),
            "visits_tonight": len(visits), "long_stay_after": long_stay,
        }

    def with_view(t, now, summ):
        cfg = {"not_served_after": not_served_after, "check_hint_after": check_hint_after,
               "plates_gone_after": plates_gone_after,
               "long_stay_after": summ["long_stay_after"]}
        return {**t, **state.view(t, now, cfg)}

    def publish_changes(now):
        tables = db.all()
        summ = summary(now, tables)
        for t in tables:
            shown_t = with_view(t, now, summ)
            if shown.get(t["id"]) != shown_t:
                shown[t["id"]] = shown_t
                msg = json.dumps({"now": now, "table": shown_t, "summary": summ,
                                  "last_event_at": last_event["at"]})
                for q in subscribers:
                    q.put_nowait(msg)
        return summ

    def save_and_publish(old, new):
        if new != old:
            visit = state.finished_visit(old, new)
            if visit:
                db.add_visit(visit)
            db.save(new)
            publish_changes(clock())
        now = clock()
        return with_view(new, now, summary(now, db.all()))

    def run_tick():
        now = clock()
        for t in db.all():
            new = state.tick(t, now, clear_after)
            if new != t:
                db.save(new)
        publish_changes(now)  # also catches alerts and hints that appear with time

    async def ticker():
        while True:
            await asyncio.sleep(1)
            run_tick()

    @asynccontextmanager
    async def lifespan(app):
        task = asyncio.create_task(ticker())
        yield
        task.cancel()

    app = FastAPI(title="TableWatch", lifespan=lifespan)
    app.state.run_tick = run_tick  # exposed for tests

    def get_or_404(table_id):
        t = db.get(table_id)
        if t is None:
            raise HTTPException(404, f"unknown table {table_id}")
        return t

    @app.post("/api/events")
    def post_event(ev: Event):
        old = get_or_404(ev.table_id)
        last_event["at"] = clock()
        new = state.observe(old, ev.people, ev.dishes, clock(), clear_after, ev.dish_count)
        return save_and_publish(old, new)

    @app.get("/api/tables")
    def get_tables():
        now = clock()
        tables = db.all()
        summ = summary(now, tables)
        return {"now": now, "clear_after_min": clear_after_min, "last_event_at": last_event["at"],
                "summary": summ, "tables": [with_view(t, now, summ) for t in tables]}

    @app.post("/api/tables/{table_id}/clear")
    def clear_table(table_id: str):
        old = get_or_404(table_id)
        return save_and_publish(old, state.mark_cleared(old, clock()))

    @app.post("/api/tables/{table_id}/served")
    def served_table(table_id: str):
        """Staff tapped a 'nobody's been here' table to say it has been looked after."""
        old = get_or_404(table_id)
        return save_and_publish(old, state.mark_served(old, clock()))

    @app.get("/api/floor")
    def get_floor():
        return floor

    @app.get("/api/stream")
    async def stream(request: Request):
        q = asyncio.Queue()
        subscribers.add(q)

        async def gen():
            try:
                yield "retry: 2000\n\n"
                while not await request.is_disconnected():
                    try:
                        msg = await asyncio.wait_for(q.get(), timeout=15)
                        yield f"data: {msg}\n\n"
                    except asyncio.TimeoutError:
                        yield ": keepalive\n\n"
            finally:
                subscribers.discard(q)

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache"})

    @app.get("/")
    def index():
        return FileResponse(ROOT / "dashboard" / "index.html")

    app.mount("/static", StaticFiles(directory=ROOT / "dashboard"), name="static")
    return app
