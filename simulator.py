"""Fake edge agent: cycles tables through realistic states so you can demo without a camera.

Each table loops:  empty -> guests seated -> guests leave (dishes left behind)
  -> usually a busser clears it quickly, sometimes nobody does and it turns red
  -> red tables wait for a tap on the dashboard (or get cleared eventually)

Stdlib only. Usage: python simulator.py [--url http://localhost:8000] [--scale 1.0]
"""
import argparse
import json
import random
import time
import urllib.request


def post(url, table_id, people, dishes):
    body = json.dumps({"table_id": table_id, "people": people, "dishes": dishes}).encode()
    req = urllib.request.Request(url + "/api/events", data=body,
                                 headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=5).read()


# (phase name, people, dishes, (min seconds, max seconds)) at scale 1.0
SEATED = ("seated", True, True, (20, 60))
LEFT_CLEARED_SOON = ("left, busser coming", False, True, (5, 15))
LEFT_NEGLECTED = ("left, nobody clearing", False, True, (60, 120))
EMPTY = ("empty", False, False, (5, 25))


def next_phase(phase):
    if phase is EMPTY:
        return SEATED
    if phase is SEATED:
        return LEFT_NEGLECTED if random.random() < 0.4 else LEFT_CLEARED_SOON
    return EMPTY


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--scale", type=float, default=1.0, help="multiply all durations (2 = slower)")
    args = ap.parse_args()

    floor = json.load(urllib.request.urlopen(args.url + "/api/floor"))
    tables = {}
    for t in floor["tables"]:
        phase = random.choice([EMPTY, SEATED, SEATED])
        tables[t["id"]] = {"phase": phase, "until": 0}

    print(f"Simulating {len(tables)} tables against {args.url} (Ctrl+C to stop)")
    while True:
        now = time.time()
        for tid, s in tables.items():
            if now < s["until"]:
                continue
            if s["until"]:  # not the first round
                s["phase"] = next_phase(s["phase"])
            name, people, dishes, (lo, hi) = s["phase"]
            s["until"] = now + random.uniform(lo, hi) * args.scale
            try:
                post(args.url, tid, people, dishes)
                print(f"{time.strftime('%H:%M:%S')}  {tid:>4}  {name}")
            except Exception as e:
                print(f"{tid}: post failed: {e}")
        time.sleep(0.5)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
