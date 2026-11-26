"""Pure table-state logic. No I/O, so it is easy to test.

The edge agent reports what it sees at a table: people present? dishes present?
The backend turns that into one of three states:

  OCCUPIED        people at the table
  FREE            no people, no dishes
  NEEDS_CLEARING  dishes, no people, for at least `clear_after` seconds

The timer only starts when guests were seated and then left dishes behind
(state was OCCUPIED). A FREE table with dishes but no guests is a freshly set
table (clean glasses, cutlery) and stays FREE. On real footage of a set dining
room the detector sees "dishes" on every set table.

While dishes sit unattended for less than `clear_after`, the table keeps its
previous state (e.g. guests stepped away briefly). `unattended_since` records
when that started.
"""

FREE = "FREE"
OCCUPIED = "OCCUPIED"
NEEDS_CLEARING = "NEEDS_CLEARING"
STATES = (FREE, OCCUPIED, NEEDS_CLEARING)


def new_table(table_id):
    return {"id": table_id, "state": FREE, "unattended_since": None, "updated_at": None}


def observe(table, people, dishes, now, clear_after):
    """Apply one observation from the edge agent. Returns the updated table."""
    t = dict(table)
    if people:
        t["state"] = OCCUPIED
        t["unattended_since"] = None
    elif dishes:
        if t["unattended_since"] is None and t["state"] == OCCUPIED:
            t["unattended_since"] = now
    else:
        t["state"] = FREE
        t["unattended_since"] = None
    t = tick(t, now, clear_after)
    t["updated_at"] = now
    return t


def tick(table, now, clear_after):
    """Promote to NEEDS_CLEARING once dishes have been unattended long enough."""
    since = table["unattended_since"]
    if table["state"] != NEEDS_CLEARING and since is not None and now - since >= clear_after:
        return {**table, "state": NEEDS_CLEARING, "updated_at": now}
    return table


def mark_cleared(table, now):
    """Staff tapped the table: it is clean and free."""
    return {**table, "state": FREE, "unattended_since": None, "updated_at": now}
