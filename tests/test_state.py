from backend.state import FREE, NEEDS_CLEARING, OCCUPIED, mark_cleared, new_table, observe, tick

N = 180  # 3 minutes


def test_people_means_occupied():
    t = observe(new_table("T1"), people=True, dishes=True, now=0, clear_after=N)
    assert t["state"] == OCCUPIED and t["unattended_since"] is None


def test_dishes_without_people_keeps_state_until_n_minutes():
    t = observe(new_table("T1"), True, True, 0, N)
    t = observe(t, False, True, 100, N)
    assert t["state"] == OCCUPIED and t["unattended_since"] == 100
    assert tick(t, 100 + N - 1, N)["state"] == OCCUPIED
    assert tick(t, 100 + N, N)["state"] == NEEDS_CLEARING


def seated():
    return observe(new_table("T1"), True, True, 0, N)


def test_repeated_unattended_observations_do_not_reset_timer():
    t = observe(seated(), False, True, 0, N)
    t = observe(t, False, True, 60, N)
    assert t["unattended_since"] == 0
    t = observe(t, False, True, N, N)
    assert t["state"] == NEEDS_CLEARING


def test_guests_returning_cancels_timer():
    t = observe(seated(), False, True, 0, N)
    t = observe(t, True, True, 60, N)
    assert t["state"] == OCCUPIED and t["unattended_since"] is None
    assert tick(t, 1000, N)["state"] == OCCUPIED


def test_no_people_no_dishes_is_free():
    t = observe(new_table("T1"), True, True, 0, N)
    t = observe(t, False, False, 10, N)
    assert t["state"] == FREE and t["unattended_since"] is None


def test_busser_clears_needs_clearing_table():
    t = observe(seated(), False, True, 0, N)
    t = tick(t, N, N)
    assert t["state"] == NEEDS_CLEARING
    assert observe(t, False, False, N + 5, N)["state"] == FREE


def test_mark_cleared():
    t = tick(observe(seated(), False, True, 0, N), N, N)
    t = mark_cleared(t, N + 1)
    assert t["state"] == FREE and t["unattended_since"] is None
    assert tick(t, N * 10, N)["state"] == FREE


def test_set_table_without_guests_stays_free():
    # Clean glasses and cutlery on a freshly set table read as "dishes".
    t = observe(new_table("T1"), False, True, 0, N)
    assert t["state"] == FREE and t["unattended_since"] is None
    assert tick(t, N * 10, N)["state"] == FREE


def test_reset_table_after_clearing_stays_free():
    t = tick(observe(seated(), False, True, 0, N), N, N)
    t = mark_cleared(t, N + 1)
    t = observe(t, False, True, N + 2, N)  # staff put clean glasses back
    assert tick(t, N * 10, N)["state"] == FREE


# --- Meal stages and timers (features 1-7) ---
from backend.state import finished_visit, mark_served, view  # noqa: E402

CFG = {"not_served_after": 600, "check_hint_after": 600, "long_stay_after": 5400}


def seat(t=None, now=0, count=3):
    return observe(t or new_table("T1"), True, True, now, N, dish_count=count)


def test_stages_through_a_meal():
    t = seat(count=3)                                        # set table: 3 items
    assert view(t, 10, CFG)["stage"] == "SEATED"
    t = observe(t, True, True, 120, N, dish_count=5)         # drinks arrive
    assert t["served_at"] == 120 and view(t, 130, CFG)["stage"] == "SERVED"
    t = observe(t, True, True, 600, N, dish_count=9)         # food
    t = observe(t, True, True, 2400, N, dish_count=3)        # plates cleared, still sitting
    assert view(t, 2410, CFG)["stage"] == "SERVED"           # a blip: not shown yet
    assert view(t, 2580, CFG)["stage"] == "FINISHING"
    t = observe(t, False, True, 2700, N, dish_count=3)       # guests leave
    assert view(t, 2710, CFG)["stage"] == "LEFT"
    t = tick(t, 2700 + N, N)
    assert view(t, 2700 + N, CFG) == {"stage": "CLEAR", "alert": "clear", "hints": []}
    t = mark_cleared(t, 3000)
    assert view(t, 3000, CFG)["stage"] == "FREE" and t["free_since"] == 3000


def test_one_extra_item_is_not_service():
    t = observe(seat(count=3), True, True, 60, N, dish_count=4)
    assert t["served_at"] is None


def test_items_taken_away_also_count_as_a_visit():
    # A party already eating when the system starts: first count is high, then
    # plates are cleared. Someone clearly came to the table, so no alert.
    t = observe(seat(count=8), True, True, 300, N, dish_count=3)
    assert t["served_at"] == 300
    t2 = observe(seat(count=4), True, True, 30, N, dish_count=3)  # small wobble: not service
    assert t2["served_at"] is None


def test_not_served_alert_and_staff_tap():
    t = seat()
    assert view(t, 599, CFG)["alert"] is None
    assert view(t, 600, CFG)["alert"] == "not_served"
    t = mark_served(t, 650)
    assert view(t, 700, CFG)["alert"] is None and view(t, 700, CFG)["stage"] == "SERVED"


def test_check_hint_is_quiet_and_delayed():
    t = observe(seat(count=3), True, True, 60, N, dish_count=8)
    t = observe(t, True, True, 1000, N, dish_count=3)
    assert view(t, 1599, CFG)["hints"] == []
    v = view(t, 1600, CFG)
    assert v["hints"] == ["check"] and v["alert"] is None
    t = observe(t, True, True, 1700, N, dish_count=6)  # dessert arrived: no longer finishing
    assert view(t, 1800, CFG)["stage"] == "SERVED"


def test_long_stay_hint():
    t = observe(seat(), True, True, 60, N, dish_count=6)
    assert "long_stay" not in view(t, 5399, CFG)["hints"]
    assert "long_stay" in view(t, 5400, CFG)["hints"]


def test_empty_time_between_parties_and_visit_record():
    t = observe(seat(now=0), True, True, 300, N, dish_count=6)
    t = observe(t, False, True, 3000, N, dish_count=6)       # guests leave
    t = tick(t, 3000 + N, N)
    old = t
    t = observe(t, False, False, 3300, N, dish_count=0)      # bussed
    assert finished_visit(old, t) == {"table_id": "T1", "seated_at": 0, "left_at": 3000,
                                      "first_service": 300, "empty_before": None}
    assert t["free_since"] == 3300
    t = observe(t, False, True, 3400, N, dish_count=3)       # reset: still free
    assert t["state"] == FREE and t["free_since"] == 3300
    t = seat(t, now=3900)
    assert t["empty_before"] == 600 and t["seated_at"] == 3900


def test_returning_guests_are_the_same_party():
    t = observe(seat(now=0), False, True, 100, N, dish_count=3)   # stepped away
    t = observe(t, True, True, 160, N, dish_count=3)
    assert t["seated_at"] == 0
