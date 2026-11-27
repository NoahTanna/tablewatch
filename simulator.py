"""Fake edge agent: plays a dinner service so you can demo without a camera.

Each table loops through a realistic meal, reporting what a camera would see
(people? dishes? how many dishes?):
  set table (glasses, cutlery) -> guests sit -> drinks/food arrive -> plates cleared
  -> guests leave -> usually bussed quickly, sometimes nobody comes and it turns red
Now and then a party is forgotten (nothing arrives) or stays very long.

Stdlib only. Usage: python simulator.py [--url http://localhost:8000] [--scale 1.0]
Durations suit ./dev.sh demo (short thresholds). --scale 2 makes everything slower.
"""
import argparse
import json
import random
import time
import urllib.request

SET = 3  # glasses and cutlery on a set table


def post(url, table_id, people, dishes, count):
    body = json.dumps({"table_id": table_id, "people": people, "dishes": dishes, "dish_count": count}).encode()
    req = urllib.request.Request(url + "/api/events", data=body, headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=5).read()


def meal():
    """One party's visit as a list of (label, people, dishes, count, seconds)."""
    forgotten = random.random() < 0.15
    long_stay = random.random() < 0.1
    steps = [("set table", False, True, SET, random.uniform(5, 30)),
             ("guests sat down", True, True, SET, random.uniform(70, 90) if forgotten else random.uniform(8, 25))]
    steps.append(("drinks arrived", True, True, SET + 2, random.uniform(8, 15)))
    steps.append(("food served", True, True, SET + 5, random.uniform(140, 180) if long_stay else random.uniform(30, 70)))
    steps.append(("plates cleared, still sitting", True, True, SET, random.uniform(10, 45)))
    neglected = random.random() < 0.35
    steps.append(("guests left, dishes remain", False, True, SET, random.uniform(45, 70) if neglected else random.uniform(5, 15)))
    steps.append(("bussed, table bare", False, False, 0, random.uniform(5, 20)))
    return steps


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--scale", type=float, default=1.0, help="multiply all durations (2 = slower)")
    args = ap.parse_args()

    floor = json.load(urllib.request.urlopen(args.url + "/api/floor"))
    tables = {}
    for t in floor["tables"]:
        steps = meal()
        start = random.randrange(len(steps) - 2)  # start mid-service
        tables[t["id"]] = {"steps": steps[start:], "until": 0}

    print(f"Simulating {len(tables)} tables against {args.url} (Ctrl+C to stop)")
    while True:
        now = time.time()
        for tid, s in tables.items():
            if now < s["until"]:
                continue
            if not s["steps"]:
                s["steps"] = meal()
            label, people, dishes, count, secs = s["steps"].pop(0)
            s["until"] = now + secs * args.scale
            try:
                post(args.url, tid, people, dishes, count)
                print(f"{time.strftime('%H:%M:%S')}  {tid:>4}  {label}")
            except Exception as e:
                print(f"{tid}: post failed: {e}")
        time.sleep(0.5)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
