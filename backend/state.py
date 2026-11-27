"""Pure table-state logic. No I/O, so it is easy to test.

The edge agent reports what it sees at a table: people present? dishes present?
how many dishes? The backend turns that into one of three states:

  OCCUPIED        people at the table
  FREE            no people, no dishes
  NEEDS_CLEARING  guests left dishes behind and nobody has been there for `clear_after` seconds

The timer only starts when guests were seated and then left dishes behind
(state was OCCUPIED). A FREE table with dishes but no guests is a freshly set
table (clean glasses, cutlery) and stays FREE.

Within a visit we also track the meal, from the dish COUNT, because pre-set
tables already have "dishes" when guests sit down:
  baseline   dishes on the table when the party sat (set glasses, cutlery)
  served_at  first time the count moved by SERVED_DELTA from the baseline:
             up (drinks, bread, food arrived) or down (staff took something away).
             Either way someone has been to the table. Erring this way keeps
             false "nothing served" alerts rare, e.g. for a party already eating
             when the system starts.
  plates_gone_since  served, and the count fell back to the baseline while the
             guests are still there (often: waiting for the check). Noisy: guests'
             arms hide plates, so this only ever drives a quiet hint.
"""

FREE = "FREE"
OCCUPIED = "OCCUPIED"
NEEDS_CLEARING = "NEEDS_CLEARING"
STATES = (FREE, OCCUPIED, NEEDS_CLEARING)

SERVED_DELTA = 2  # change in dish count that means "someone has been to the table"
PLATES_GONE_SHOW_AFTER = 180  # seconds before "plates gone" shows on the tile

VISIT_FIELDS = {"seated_at": None, "served_at": None, "baseline": None, "peak": None,
                "plates_gone_since": None, "empty_before": None}


def new_table(table_id):
    return {"id": table_id, "state": FREE, "unattended_since": None, "updated_at": None,
            "free_since": None, "dish_count": None, **VISIT_FIELDS}


def observe(table, people, dishes, now, clear_after, dish_count=None):
    """Apply one observation from the edge agent. Returns the updated table."""
    t = {**new_table(table["id"]), **table}
    if dish_count is not None:
        t["dish_count"] = dish_count
    if people:
        if t["state"] != OCCUPIED:  # a new party sat down
            empty = now - t["free_since"] if t["free_since"] is not None else None
            t.update(VISIT_FIELDS, seated_at=now, empty_before=empty, free_since=None)
        t["state"] = OCCUPIED
        t["unattended_since"] = None
        _track_meal(t, now)
    elif dishes:
        if t["unattended_since"] is None and t["state"] == OCCUPIED:
            t["unattended_since"] = now
    else:
        _to_free(t, now)
    t = tick(t, now, clear_after)
    t["updated_at"] = now
    return t


def _track_meal(t, now):
    count = t["dish_count"]
    if count is None:
        return
    if t["baseline"] is None:
        t["baseline"] = t["peak"] = count
    if t["served_at"] is None and abs(count - t["baseline"]) >= SERVED_DELTA:
        t["served_at"] = now
    t["peak"] = max(t["peak"], count)
    plates_gone = (t["served_at"] is not None and count <= t["baseline"]
                   and t["peak"] - count >= SERVED_DELTA)
    if not plates_gone:
        t["plates_gone_since"] = None
    elif t["plates_gone_since"] is None:
        t["plates_gone_since"] = now


def _to_free(t, now):
    if t["state"] != FREE:  # the table turned: start counting empty time
        t["free_since"] = now
    t["state"] = FREE
    t["unattended_since"] = None
    t.update(VISIT_FIELDS)


def tick(table, now, clear_after):
    """Promote to NEEDS_CLEARING once dishes have been unattended long enough."""
    since = table["unattended_since"]
    if table["state"] != NEEDS_CLEARING and since is not None and now - since >= clear_after:
        return {**table, "state": NEEDS_CLEARING, "updated_at": now}
    return table


def mark_cleared(table, now):
    """Staff tapped the table: it is clean and free."""
    t = {**new_table(table["id"]), **table}
    _to_free(t, now)
    t["updated_at"] = now
    return t


def mark_served(table, now):
    """Staff tapped a 'nobody's been here' table: someone has looked after it."""
    if table.get("state") != OCCUPIED or table.get("served_at") is not None:
        return table
    return {**table, "served_at": now, "updated_at": now}


def finished_visit(old, new):
    """If this change ended a party's visit, return a record of it, else None."""
    seated = old.get("seated_at")
    if seated is None or new.get("seated_at") == seated:
        return None
    left = old.get("unattended_since") or new["updated_at"]
    served = old.get("served_at")
    return {"table_id": old["id"], "seated_at": seated, "left_at": left,
            "first_service": served - seated if served is not None else None,
            "empty_before": old.get("empty_before")}


def view(t, now, cfg):
    """What the dashboard shows for one table: stage, quiet hints and loud alerts.

    cfg: not_served_after, check_hint_after, long_stay_after, plates_gone_after (seconds)."""
    stage, alert, hints = "FREE", None, []
    if t["state"] == NEEDS_CLEARING:
        stage, alert = "CLEAR", "clear"
    elif t["state"] == OCCUPIED and t["unattended_since"] is not None:
        stage = "LEFT"
    elif t["state"] == OCCUPIED:
        if t["served_at"] is None:
            stage = "SEATED"
            if t["seated_at"] is not None and now - t["seated_at"] >= cfg["not_served_after"]:
                alert = "not_served"
        elif t["plates_gone_since"] is not None and now - t["plates_gone_since"] >= cfg.get("plates_gone_after", PLATES_GONE_SHOW_AFTER):
            stage = "FINISHING"  # shown only once it has lasted: the count is noisy
            if now - t["plates_gone_since"] >= cfg["check_hint_after"]:
                hints.append("check")
        else:
            stage = "SERVED"
        if t["seated_at"] is not None and now - t["seated_at"] >= cfg["long_stay_after"]:
            hints.append("long_stay")
    return {"stage": stage, "alert": alert, "hints": hints}
