"""Made-up service history, for trying the Reports tab and for the browser demo.

  python tools/sample_history.py demo.db      # add 14 past nights to a database

Never point this at a real restaurant's database: it inserts invented parties.
"""
import random
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.db import DB  # noqa: E402

M = 60
CLEAR_AFTER = 3 * M


def night_visits(day, table_ids, rng):
    """Parties for one dinner service (5 PM to about 11 PM)."""
    weekend = day.weekday() in (4, 5)     # Friday, Saturday
    slow = day.weekday() in (0, 1)        # Monday, Tuesday
    visits = []
    for tid in table_ids:
        t = datetime.combine(day, datetime.min.time()).replace(hour=17).timestamp() + rng.uniform(0, 50) * M
        empty = None
        while t < datetime.combine(day, datetime.min.time()).replace(hour=22, minute=15).timestamp():
            stay = rng.uniform(70, 110) * M if weekend else rng.uniform(50, 90) * M
            r = rng.random()
            first = None if r < 0.03 else rng.uniform(10, 20) * M if r < 0.15 else rng.uniform(2, 9) * M
            wait = rng.uniform(4, 12) * M if rng.random() < (0.3 if weekend else 0.2) else rng.uniform(0.5, 3) * M
            left = t + stay
            visits.append({"table_id": tid, "seated_at": t, "left_at": left, "first_service": first,
                           "empty_before": empty, "cleared_at": left + wait, "went_red": wait >= CLEAR_AFTER})
            empty = rng.uniform(2, 10) * M if weekend else rng.uniform(15, 50) * M if slow else rng.uniform(5, 25) * M
            t = left + wait + empty
    return visits


def history(table_ids, nights=14, today=None, seed=7):
    """{date: [visits]} for the `nights` service days before `today` (not including it)."""
    rng = random.Random(seed)
    today = today or date.today()
    return {today - timedelta(days=k): night_visits(today - timedelta(days=k), table_ids, rng) for k in range(nights, 0, -1)}


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "demo.db"
    import json
    floor = json.loads((Path(__file__).resolve().parent.parent / "config" / "floor.json").read_text())
    db = DB(path)
    n = 0
    for visits in history([t["id"] for t in floor["tables"]]).values():
        for v in visits:
            db.add_visit(v)
            n += 1
    print(f"added {n} made-up parties over 14 nights to {path}")


if __name__ == "__main__":
    main()
