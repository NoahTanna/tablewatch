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


def test_repeated_unattended_observations_do_not_reset_timer():
    t = observe(new_table("T1"), False, True, 0, N)
    t = observe(t, False, True, 60, N)
    assert t["unattended_since"] == 0
    t = observe(t, False, True, N, N)
    assert t["state"] == NEEDS_CLEARING


def test_guests_returning_cancels_timer():
    t = observe(new_table("T1"), False, True, 0, N)
    t = observe(t, True, True, 60, N)
    assert t["state"] == OCCUPIED and t["unattended_since"] is None
    assert tick(t, 1000, N)["state"] == OCCUPIED


def test_no_people_no_dishes_is_free():
    t = observe(new_table("T1"), True, True, 0, N)
    t = observe(t, False, False, 10, N)
    assert t["state"] == FREE and t["unattended_since"] is None


def test_busser_clears_needs_clearing_table():
    t = observe(new_table("T1"), False, True, 0, N)
    t = tick(t, N, N)
    assert t["state"] == NEEDS_CLEARING
    assert observe(t, False, False, N + 5, N)["state"] == FREE


def test_mark_cleared():
    t = tick(observe(new_table("T1"), False, True, 0, N), N, N)
    t = mark_cleared(t, N + 1)
    assert t["state"] == FREE and t["unattended_since"] is None
    assert tick(t, N * 10, N)["state"] == FREE
