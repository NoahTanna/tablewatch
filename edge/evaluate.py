"""Compare the agent's output with hand-labeled ground truth for one recorded video.

Both files are CSV with header  time_s,table_id,people,dishes  and one row per change
(give every table a row at time 0 in the labels). Produce predictions with:
  python -m edge.agent --source dinner.mp4 --dry-run --log predictions.csv
then:
  python -m edge.evaluate labels.csv predictions.csv [--clear-after-min 3]
"""
import argparse
import csv
from collections import defaultdict

from backend import state


def load(path):
    rows = defaultdict(list)
    for r in csv.DictReader(open(path)):
        rows[r["table_id"]].append((float(r["time_s"]), r["people"] == "1", r["dishes"] == "1"))
    return {t: sorted(v) for t, v in rows.items()}


def value_at(changes, t, idx):
    """Value of signal idx (1=people, 2=dishes) at time t, or None before the first row."""
    v = None
    for row in changes:
        if row[0] > t:
            break
        v = row[idx]
    return v


def alerts(changes, clear_after, end):
    """Times a table turned NEEDS_CLEARING, using the same rules as the backend."""
    table, out = state.new_table("x"), []
    events = [(t, p, d) for t, p, d in changes]
    t = 0.0
    while t <= end:
        while events and events[0][0] <= t:
            _, p, d = events.pop(0)
            table = state.observe(table, p, d, t, clear_after)
        before = table["state"]
        table = state.tick(table, t, clear_after)
        if table["state"] == state.NEEDS_CLEARING and before != state.NEEDS_CLEARING:
            out.append(t)
        t += 1
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("labels")
    ap.add_argument("predictions")
    ap.add_argument("--clear-after-min", type=float, default=3)
    ap.add_argument("--match-window", type=float, default=120, help="seconds to match an alert")
    args = ap.parse_args(argv)
    labels, preds = load(args.labels), load(args.predictions)
    end = max(r[0] for rows in list(labels.values()) + list(preds.values()) for r in rows) + 60
    clear_after = args.clear_after_min * 60

    print(f"{'table':<8}{'people ok':>11}{'dishes ok':>11}{'alerts':>8}{'caught':>8}{'false':>7}{'avg delay':>11}")
    totals = defaultdict(float)
    for tid in sorted(labels):
        lab, pred = labels[tid], preds.get(tid, [])
        ok = [0, 0]
        secs = int(end)
        for t in range(secs):
            for i, idx in enumerate((1, 2)):
                ok[i] += value_at(lab, t, idx) == value_at(pred, t, idx)
        truth, got = alerts(lab, clear_after, end), alerts(pred, clear_after, end)
        caught, delays, unused = 0, [], list(got)
        for a in truth:
            match = next((g for g in unused if a - 10 <= g <= a + args.match_window), None)
            if match is not None:
                unused.remove(match)
                caught += 1
                delays.append(match - a)
        delay = f"{sum(delays) / len(delays):+.0f}s" if delays else "-"
        print(f"{tid:<8}{ok[0] / secs:>11.0%}{ok[1] / secs:>11.0%}{len(truth):>8}{caught:>8}{len(unused):>7}{delay:>11}")
        for k, v in (("secs", secs), ("p", ok[0]), ("d", ok[1]), ("truth", len(truth)),
                     ("caught", caught), ("false", len(unused))):
            totals[k] += v
    if totals["secs"]:
        print(f"{'ALL':<8}{totals['p'] / totals['secs']:>11.0%}{totals['d'] / totals['secs']:>11.0%}"
              f"{int(totals['truth']):>8}{int(totals['caught']):>8}{int(totals['false']):>7}")
    print("\npeople/dishes ok = share of seconds the agent agreed with the labels "
          "(the agent's first few samples count as wrong).\nalerts = NEEDS_CLEARING moments in the labels; "
          "caught = matched by the agent; false = agent alerts with no real one; "
          "delay = agent alert minus true alert.")


if __name__ == "__main__":
    main()
