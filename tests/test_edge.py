import csv
import json

import cv2
import numpy as np
import pytest

from edge import agent, evaluate
from edge.debounce import Debouncer
from edge.detector import _decode, _grids
from edge.zones import inside, observe_tables

SQUARE = [(0, 0), (100, 0), (100, 100), (0, 100)]
ZONES = {"T1": SQUARE, "T2": [(200, 0), (300, 0), (300, 100), (200, 100)]}


def test_point_in_polygon():
    assert inside((50, 50), SQUARE)
    assert not inside((150, 50), SQUARE)
    tri = [(0, 0), (100, 0), (0, 100)]
    assert inside((10, 10), tri) and not inside((90, 90), tri)


def test_observe_tables_assigns_people_and_dishes():
    dets = [("person", 0.9, (10, 10, 60, 90)), ("dish", 0.8, (220, 40, 240, 60))]
    assert observe_tables(dets, ZONES) == {"T1": (True, False), "T2": (False, True)}


def test_person_counts_by_bottom_center():
    # Box center is above the zone, but the person's feet/chair are inside it.
    dets = [("person", 0.9, (20, -150, 60, 50))]
    assert observe_tables(dets, ZONES)["T1"] == (True, False)


def test_debounce_needs_consecutive_samples():
    d = Debouncer(confirm=3)
    assert d.update("T1", False, False) is None
    assert d.update("T1", False, False) is None
    assert d.update("T1", False, False) == (False, False)
    # A waiter passing for one sample does not count.
    assert d.update("T1", True, False) is None
    assert d.update("T1", False, False) is None
    # Guests sit down for real.
    for _ in range(2):
        assert d.update("T1", True, True) is None
    assert d.update("T1", True, True) == (True, True)
    assert d.current("T1") == (True, True) and d.known() == ["T1"]


def test_decode_finds_planted_box():
    grids, strides = _grids(640)
    out = np.full((len(grids), 85), -10.0, dtype=np.float32)
    out[:, 4:] = 0.0
    i = 100  # a stride-8 cell at grid (x=20, y=1)
    out[i, :4] = [0.5, 0.5, np.log(4), np.log(8)]  # center (164, 12), size 32x64 pixels
    out[i, 4] = 0.9
    out[i, 5 + 41] = 0.95  # "cup"
    res = _decode(out, 1.0, grids, strides, 0.35)
    assert len(res) == 1
    kind, score, (x1, y1, x2, y2) = res[0]
    assert kind == "dish" and score == pytest.approx(0.855)
    assert (x1, y1, x2, y2) == pytest.approx((148, -20, 180, 44))


def test_agent_on_video_with_fake_detector(tmp_path, monkeypatch):
    """Frame color encodes the scene: red=guests at T1, green=dishes only, black=empty."""
    path = str(tmp_path / "v.avi")
    w = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"MJPG"), 5, (320, 120))
    for color, secs in (((0, 0, 255), 20), ((0, 255, 0), 20), ((0, 0, 0), 20)):
        for _ in range(secs * 5):
            w.write(np.full((120, 320, 3), color, np.uint8))
    w.release()

    class FakeDetector:
        def __init__(self, *a, **k):
            pass

        def detect(self, frame):
            b, g, r = frame[60, 160]
            if r > 128:
                return [("person", 0.9, (10, 10, 60, 90)), ("dish", 0.9, (40, 40, 50, 50))]
            if g > 128:
                return [("dish", 0.9, (40, 40, 50, 50))]
            return []

    zones = tmp_path / "zones.json"
    zones.write_text(json.dumps({"zones": {k: v for k, v in ZONES.items()}}))
    monkeypatch.setattr(agent, "Detector", FakeDetector)
    log = tmp_path / "pred.csv"
    agent.main(["--source", path, "--zones", str(zones), "--model", "x", "--every", "2",
                "--confirm", "2", "--dry-run", "--log", str(log)])
    rows = [(r["table_id"], r["people"], r["dishes"]) for r in csv.DictReader(open(log))]
    assert [r for r in rows if r[0] == "T1"] == [("T1", "1", "1"), ("T1", "0", "1"), ("T1", "0", "0")]
    assert [r for r in rows if r[0] == "T2"] == [("T2", "0", "0")]


def test_evaluate_alerts_and_report(tmp_path, capsys):
    labels = tmp_path / "labels.csv"
    preds = tmp_path / "pred.csv"
    labels.write_text("time_s,table_id,people,dishes\n0,T1,1,1\n100,T1,0,1\n500,T1,0,0\n")
    preds.write_text("time_s,table_id,people,dishes\n6,T1,1,1\n109,T1,0,1\n506,T1,0,0\n")
    changes = evaluate.load(str(labels))["T1"]
    assert evaluate.alerts(changes, 180, 600) == [280]
    evaluate.main([str(labels), str(preds)])
    out = capsys.readouterr().out
    line = next(l for l in out.splitlines() if l.startswith("T1"))
    assert line.split()[3:] == ["1", "1", "0", "+9s"]
