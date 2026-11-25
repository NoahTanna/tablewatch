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


class Event(BaseModel):
    """What the edge agent sees at one table. Never images, just two booleans."""
    table_id: str
    people: bool
    dishes: bool


def create_app(db_path=None, floor_path=None, clear_after_min=None, clock=time.time):
    db_path = db_path or os.environ.get("TABLEWATCH_DB", str(ROOT / "tablewatch.db"))
    floor_path = floor_path or os.environ.get("TABLEWATCH_FLOOR", str(ROOT / "config" / "floor.json"))
    if clear_after_min is None:
        clear_after_min = float(os.environ.get("CLEAR_AFTER_MIN", "3"))
    clear_after = clear_after_min * 60

    floor = json.loads(Path(floor_path).read_text())
    db = DB(db_path)
    ids = [t["id"] for t in floor["tables"]]
    for tid in ids:
        db.ensure(state.new_table(tid))
    db.remove_except(ids)

    subscribers = set()  # one asyncio.Queue per connected dashboard
    last_event = {"at": None}  # when the camera side last reported (in memory)

    def publish(table):
        msg = json.dumps({"now": clock(), "table": table})
        for q in subscribers:
            q.put_nowait(msg)

    def save_and_publish(old, new):
        if new != old:
            db.save(new)
            publish(new)

    def run_tick():
        now = clock()
        for t in db.all():
            save_and_publish(t, state.tick(t, now, clear_after))

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
        new = state.observe(old, ev.people, ev.dishes, clock(), clear_after)
        save_and_publish(old, new)
        return new

    @app.get("/api/tables")
    def get_tables():
        return {"now": clock(), "clear_after_min": clear_after_min,
                "last_event_at": last_event["at"], "tables": db.all()}

    @app.post("/api/tables/{table_id}/clear")
    def clear_table(table_id: str):
        old = get_or_404(table_id)
        new = state.mark_cleared(old, clock())
        save_and_publish(old, new)
        return new

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
