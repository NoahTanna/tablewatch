"""SETUP ONLY: save one still frame so you can draw table zones on it.

This is the only thing in TableWatch that writes an image to disk. Take it when the
dining room is empty, use it in tools/zone_editor.html, then delete it.
  python -m edge.snapshot --source rtsp://... --out room.jpg
"""
import argparse

import cv2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True, help="video file or rtsp:// URL")
    ap.add_argument("--out", default="room.jpg")
    args = ap.parse_args()
    cap = cv2.VideoCapture(args.source)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise SystemExit(f"could not read a frame from {args.source}")
    cv2.imwrite(args.out, frame)
    h, w = frame.shape[:2]
    print(f"saved {args.out} ({w}x{h}). Delete it once your zones are drawn.")


if __name__ == "__main__":
    main()
