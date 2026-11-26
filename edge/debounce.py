"""Ignore flickers: a value (people / dishes) only changes after it is seen
`confirm` samples in a row. A waiter walking past does not seat a table, and a
glass hidden for one frame does not clear it.

Dishes disappearing needs twice as many samples: if a dirty table wrongly reads
as clean, it goes green and won't turn red again until new guests sit there."""


class Debouncer:
    def __init__(self, confirm=3):
        self.confirm = confirm
        self.stable = {}  # (table, signal) -> bool
        self.streak = {}  # (table, signal) -> (candidate value, count)

    def update(self, table_id, people, dishes):
        """Feed one raw observation. Returns (people, dishes) if the stable value
        changed (or became known for the first time), else None."""
        changed = False
        for signal, value in (("people", people), ("dishes", dishes)):
            key = (table_id, signal)
            cand, count = self.streak.get(key, (value, 0))
            count = count + 1 if cand == value else 1
            self.streak[key] = (value, count)
            needed = self.confirm * 2 if (signal == "dishes" and not value and key in self.stable) else self.confirm
            if count >= needed and self.stable.get(key) != value:
                self.stable[key] = value
                changed = True
        if changed and all((table_id, s) in self.stable for s in ("people", "dishes")):
            return self.current(table_id)
        return None

    def current(self, table_id):
        return self.stable[(table_id, "people")], self.stable[(table_id, "dishes")]

    def known(self):
        return [t for t in {k[0] for k in self.stable}
                if all((t, s) in self.stable for s in ("people", "dishes"))]
