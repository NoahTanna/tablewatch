"""Map detections to tables using per-table polygons from config/zones.json.

Draw each zone around the table AND its chairs, so seated guests fall inside it.
A person counts for a table if the center or bottom-center of their box is in the zone.
A dish counts if the center of its box is in the zone.
"""
import json


def load_zones(path):
    data = json.load(open(path))
    return {tid: [tuple(p) for p in poly] for tid, poly in data["zones"].items()}


def inside(pt, poly):
    """Ray-casting point-in-polygon."""
    x, y = pt
    hit = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            hit = not hit
        j = i
    return hit


def observe_tables(detections, zones):
    """-> {table_id: (people, dishes)} for every zone."""
    obs = {tid: [False, False] for tid in zones}
    for kind, _score, (x1, y1, x2, y2) in detections:
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        points = [(cx, cy), (cx, y2)] if kind == "person" else [(cx, cy)]
        for tid, poly in zones.items():
            if any(inside(p, poly) for p in points):
                obs[tid][0 if kind == "person" else 1] = True
    return {tid: tuple(v) for tid, v in obs.items()}
