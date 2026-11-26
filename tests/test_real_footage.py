"""Accuracy check on real restaurant footage (see eval/mixkit-4385/README.md).
Skipped unless the clip and the model have been downloaded."""
import csv
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CLIP = ROOT / "eval" / "mixkit-4385"
VIDEO, MODEL = CLIP / "4385.mp4", ROOT / "models" / "yolox_s.onnx"


@pytest.mark.skipif(not (VIDEO.exists() and MODEL.exists()), reason="clip or model not downloaded")
def test_detector_accuracy_on_real_restaurant_clip():
    from edge.agent import video_frames
    from edge.detector import Detector
    from edge.zones import load_zones, observe_tables

    zones = load_zones(CLIP / "zones.json")
    labels = {(int(r["sample"]), r["table_id"]): (r["people"] == "1", r["dishes"] == "1")
              for r in csv.DictReader(open(CLIP / "labels_samples.csv"))}
    det = Detector(str(MODEL))
    right = {"people": 0, "dishes": 0}
    dish_false_alarms, n = 0, 0
    for i, (_t, frame) in enumerate(video_frames(str(VIDEO), 0.5)):
        for tid, (people, dishes) in observe_tables(det.detect_tables(frame, zones), zones).items():
            truth = labels[(i, tid)]
            right["people"] += people == truth[0]
            right["dishes"] += dishes == truth[1]
            dish_false_alarms += dishes and not truth[1]
            n += 1
    assert n == 120
    assert right["people"] / n >= 0.88
    assert right["dishes"] / n >= 0.93
    # A phantom dish after guests leave would turn a clean table red.
    assert dish_false_alarms <= 2
