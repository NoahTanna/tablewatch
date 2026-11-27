"""Map detections to tables using per-table polygons from config/zones.json.

Draw each zone around the table AND its chairs, so seated guests fall inside it.
A person counts for the ONE table whose zone covers the largest share of their box
(at least a third of it). A camera looking down at an angle makes a seated guest
overlap the neighboring tables' zones, so "touches the zone" is not enough.
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


def person_table(box, zones, grid=7, min_share=1 / 3):
    """Table whose zone covers the largest share of this person's box, or None."""
    x1, y1, x2, y2 = box
    points = [(x1 + (x2 - x1) * (i + 0.5) / grid, y1 + (y2 - y1) * (j + 0.5) / grid)
              for i in range(grid) for j in range(grid)]
    best, best_share = None, min_share
    for tid, poly in zones.items():
        share = sum(inside(p, poly) for p in points) / len(points)
        if share >= best_share:
            best, best_share = tid, share
    return best


def observe_tables(detections, zones):
    """-> {table_id: (people, dishes)} for every zone."""
    obs = {tid: [False, False] for tid in zones}
    for kind, _score, (x1, y1, x2, y2) in detections:
        if kind == "person":
            tid = person_table((x1, y1, x2, y2), zones)
            if tid is not None:
                obs[tid][0] = True
        else:
            center = ((x1 + x2) / 2, (y1 + y2) / 2)
            for tid, poly in zones.items():
                if inside(center, poly):
                    obs[tid][1] = True
    return {tid: tuple(v) for tid, v in obs.items()}


def count_dishes(detections, zones):
    """-> {table_id: number of dishes whose center is in the zone}."""
    counts = {tid: 0 for tid in zones}
    for kind, _score, (x1, y1, x2, y2) in detections:
        if kind != "dish":
            continue
        center = ((x1 + x2) / 2, (y1 + y2) / 2)
        for tid, poly in zones.items():
            if inside(center, poly):
                counts[tid] += 1
    return counts
