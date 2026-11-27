"""Edge agent: camera or video -> detections -> per-table people/dishes -> backend.

Recorded video (Milestone 2, evaluation):
  python -m edge.agent --source dinner.mp4 --log predictions.csv --dry-run
Live camera (Milestone 3):
  python -m edge.agent --source rtsp://user:pass@192.168.1.50/stream1 --backend http://localhost:8000

Privacy: frames live only in memory (the latest one for a live camera) and are dropped
after detection. Only table_id + two booleans ever leave this process. No audio is read.
"""
import argparse
import csv
import json
import logging
import statistics
import threading
import time
import urllib.request
from collections import defaultdict, deque

import cv2

from edge.debounce import Debouncer
from edge.detector import Detector
from edge.zones import count_dishes, load_zones, observe_tables

COUNT_WINDOW = 5  # dish counts are noisy (arms hide plates): send the median of the last 5

log = logging.getLogger("edge")


class LatestFrame:
    """Reads a live stream in a background thread and keeps only the newest frame,
    so a slow detector never builds up a backlog. Reconnects if the stream drops."""

    def __init__(self, url):
        self.url, self.frame, self.lock = url, None, threading.Lock()
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        delay = 1
        while True:
            cap = cv2.VideoCapture(self.url)
            while cap.isOpened():
                ok, frame = cap.read()
                if not ok:
                    break
                delay = 1
                with self.lock:
                    self.frame = frame
            cap.release()
            with self.lock:
                self.frame = None
            log.warning("camera stream lost, retrying in %ss", delay)
            time.sleep(delay)
            delay = min(delay * 2, 30)

    def take(self):
        with self.lock:
            frame, self.frame = self.frame, None
        return frame


def video_frames(path, every):
    """Yield (video_time_s, frame) every `every` seconds of a recorded video, as fast as possible."""
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise SystemExit(f"cannot open video {path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    step, i = max(1, round(fps * every)), 0
    while True:
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ok, frame = cap.read()
        if not ok:
            break
        yield i / fps, frame
        i += step
    cap.release()


def live_frames(url, every):
    """Yield (wall_time_s, latest frame) every `every` seconds from a live stream."""
    source = LatestFrame(url)
    while True:
        start = time.time()
        frame = source.take()
        if frame is not None:
            yield start, frame
        time.sleep(max(0.0, every - (time.time() - start)))


def post(backend, table_id, people, dishes, dish_count=None):
    body = json.dumps({"table_id": table_id, "people": people, "dishes": dishes,
                       "dish_count": dish_count}).encode()
    req = urllib.request.Request(backend + "/api/events", data=body,
                                 headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=5).read()


def main(argv=None):
    ap = argparse.ArgumentParser(description="TableWatch edge agent")
    ap.add_argument("--source", required=True, help="video file path or rtsp:// URL")
    ap.add_argument("--zones", default="config/zones.json")
    ap.add_argument("--model", default="models/yolox_s.onnx")
    ap.add_argument("--backend", default="http://localhost:8000")
    ap.add_argument("--every", type=float, default=3, help="seconds between sampled frames")
    ap.add_argument("--confirm", type=int, default=3, help="samples in a row before a change counts")
    ap.add_argument("--conf", type=float, default=0.35, help="confidence needed for a person")
    ap.add_argument("--dish-conf", type=float, default=0.25, help="confidence needed for a dish")
    ap.add_argument("--resync", type=float, default=30, help="re-send all table states every N s")
    ap.add_argument("--log", help="write stable changes to this CSV (time_s,table_id,people,dishes)")
    ap.add_argument("--dry-run", action="store_true", help="do not contact the backend")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    zones = load_zones(args.zones)
    detector = Detector(args.model, conf=args.conf, dish_conf=args.dish_conf)
    debouncer = Debouncer(args.confirm)
    live = args.source.startswith(("rtsp://", "rtsps://", "http://", "https://"))
    frames = live_frames(args.source, args.every) if live else video_frames(args.source, args.every)
    out = csv.writer(open(args.log, "w", newline="")) if args.log else None
    if out:
        out.writerow(["time_s", "table_id", "people", "dishes", "dish_count"])
    last_sync = 0.0
    recent = defaultdict(lambda: deque(maxlen=COUNT_WINDOW))  # table -> last raw dish counts
    sent_count = {}  # table -> smoothed count last sent

    def send(tid, people, dishes, count):
        if args.dry_run:
            return
        try:
            post(args.backend, tid, people, dishes, count)
        except Exception as e:  # backend down: the next resync will catch it up
            log.warning("could not reach backend: %s", e)

    log.info("watching %d tables from %s", len(zones), "camera" if live else args.source)
    for t, frame in frames:
        detections = detector.detect_tables(frame, zones)
        del frame  # never kept
        observations = observe_tables(detections, zones)
        for tid, n in count_dishes(detections, zones).items():
            recent[tid].append(n)
        for tid, (people, dishes) in observations.items():
            changed = debouncer.update(tid, people, dishes)
            count = int(statistics.median(recent[tid]))
            if changed is None and tid in debouncer.known() and count != sent_count.get(tid):
                changed = debouncer.current(tid)  # only the dish count moved
            if changed is not None:
                sent_count[tid] = count
                when = time.strftime("%H:%M:%S", time.localtime(t)) if live else f"t={t:.0f}s"
                log.info("%s %s people=%s dishes=%s count=%s", when, tid, *changed, count)
                if out:
                    out.writerow([round(t, 1), tid, int(changed[0]), int(changed[1]), count])
                send(tid, *changed, count)
        if live and time.time() - last_sync >= args.resync:
            last_sync = time.time()
            for tid in debouncer.known():
                send(tid, *debouncer.current(tid), sent_count.get(tid))


if __name__ == "__main__":
    main()
