"""End-of-night and weekly reports, built from finished parties (the visits table).

Pure functions: give them visits and the floor, get back plain numbers (seconds)
for the dashboard to format. Only times are used: no people, no per-server data.

A "night" is a service day that runs 04:00 to 04:00 local time, so a party that
sits down at 00:30 counts toward the evening before.
"""
from datetime import date, datetime, timedelta

DAY_STARTS_AT = 4  # local hour


def night_bounds(day):
    start = datetime.combine(day, datetime.min.time()) + timedelta(hours=DAY_STARTS_AT)
    return start.timestamp(), (start + timedelta(days=1)).timestamp()


def service_day(ts):
    return (datetime.fromtimestamp(ts) - timedelta(hours=DAY_STARTS_AT)).date()


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def _label(day):
    return f"{day:%A}, {day:%b} {day.day}"


def _clean(visits, min_visit):
    return [v for v in visits if v["left_at"] - v["seated_at"] >= min_visit]


def _busy_hours(visits, n_tables):
    """Share of tables with a party, hour by hour (only hours with any guests)."""
    if not visits or not n_tables:
        return []
    first = datetime.fromtimestamp(min(v["seated_at"] for v in visits)).replace(minute=0, second=0, microsecond=0)
    last = datetime.fromtimestamp(max(v["left_at"] for v in visits))
    hours, t = [], first
    while t <= last:
        a, b = t.timestamp(), (t + timedelta(hours=1)).timestamp()
        used = sum(max(0, min(b, v["left_at"]) - max(a, v["seated_at"])) for v in visits)
        hours.append({"hour": t.hour, "busy": min(1.0, used / (3600 * n_tables))})
        t += timedelta(hours=1)
    return hours


def night(visits, day, floor_tables, not_served_after, min_visit=120):
    """Report for one service day. visits: parties that sat down that night."""
    vs = _clean(visits, min_visit)
    names = {t["id"]: t.get("name", t["id"]) for t in floor_tables}
    stays = [v["left_at"] - v["seated_at"] for v in vs]
    clear_waits = [(v["cleared_at"] - v["left_at"], v) for v in vs if v["cleared_at"] is not None]
    empties = [v["empty_before"] for v in vs if v["empty_before"] is not None]
    late_starts = [v for v in vs if v["first_service"] is None or v["first_service"] >= not_served_after]
    dirty_total = sum(w for w, _ in clear_waits)
    idle_total = dirty_total + sum(empties)
    avg_stay = _mean(stays)
    worst = max(clear_waits, key=lambda x: x[0], default=None)
    slow = sorted((v for v in vs if v["first_service"] is not None), key=lambda v: -v["first_service"])[:3]

    def spot(v, seconds):
        return {"table": names.get(v["table_id"], v["table_id"]), "seconds": seconds, "at": v["seated_at"]}

    tables = []
    for t in floor_tables:
        mine = [v for v in vs if v["table_id"] == t["id"]]
        waits = [w for w, v in clear_waits if v["table_id"] == t["id"]]
        tables.append({"table": names[t["id"]], "seats": t.get("seats"), "parties": len(mine),
                       "avg_stay": _mean(v["left_at"] - v["seated_at"] for v in mine),
                       "avg_first_service": _mean(v["first_service"] for v in mine),
                       "avg_clear_wait": _mean(waits),
                       "went_red": sum(1 for v in mine if v["went_red"])})
    return {
        "day": day.isoformat(), "label": _label(day),
        "parties": len(vs), "tables_total": len(floor_tables),
        "turns_per_table": len(vs) / len(floor_tables) if floor_tables else None,
        "avg_stay": avg_stay,
        "avg_first_service": _mean(v["first_service"] for v in vs),
        "slowest_first_service": [spot(v, v["first_service"]) for v in slow],
        "late_starts": len(late_starts), "late_after": not_served_after,
        "avg_clear_wait": _mean(w for w, _ in clear_waits),
        "went_red": sum(1 for v in vs if v["went_red"]),
        "worst_clear_wait": spot(worst[1], worst[0]) if worst else None,
        "avg_empty_between": _mean(empties),
        "idle_table_time": idle_total,
        "dirty_table_time": dirty_total,
        # Rough: how many more average parties that idle table time could have seated
        # on a night with people waiting. Shown as an estimate, never as lost money.
        "extra_parties_estimate": idle_total / avg_stay if avg_stay else None,
        "busy_hours": _busy_hours(vs, len(floor_tables)),
        "tables": tables,
    }


def week(visits_by_day, floor_tables, not_served_after, min_visit=120):
    """visits_by_day: {date: [visits]} for 7 consecutive nights, oldest first."""
    nights = []
    for day, visits in visits_by_day.items():
        n = night(visits, day, floor_tables, not_served_after, min_visit)
        busiest = max(n["busy_hours"], key=lambda h: h["busy"], default=None)
        nights.append({k: n[k] for k in ("day", "label", "parties", "avg_stay", "avg_first_service", "late_starts",
                                         "avg_clear_wait", "went_red", "avg_empty_between", "idle_table_time",
                                         "extra_parties_estimate")}
                      | {"short": f"{day:%a}", "busiest_hour": busiest["hour"] if busiest and busiest["busy"] > 0 else None})
    active = [n for n in nights if n["parties"]]
    slowest = max((n for n in active if n["avg_clear_wait"] is not None), key=lambda n: n["avg_clear_wait"], default=None)
    return {
        "start": nights[0]["day"] if nights else None, "end": nights[-1]["day"] if nights else None,
        "nights": nights,
        "parties": sum(n["parties"] for n in nights),
        "went_red": sum(n["went_red"] for n in nights),
        "late_starts": sum(n["late_starts"] for n in nights), "late_after": not_served_after,
        "idle_table_time": sum(n["idle_table_time"] for n in nights),
        "extra_parties_estimate": sum(n["extra_parties_estimate"] or 0 for n in nights),
        "slowest_clearing_night": slowest["label"] if slowest else None,
    }


def parse_day(value, now_ts):
    return date.fromisoformat(value) if value else service_day(now_ts)
